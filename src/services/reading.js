import { createHash } from 'node:crypto';
import { db } from '../db/index.js';

const WIKI_SEARCH = 'https://en.wikipedia.org/w/rest.php/v1/search/page';
const WIKI_SUMMARY = 'https://en.wikipedia.org/api/rest_v1/page/summary';

function cacheGet(hash) {
  const row = db.prepare('SELECT response_json FROM resource_cache WHERE provider = ? AND request_hash = ?')
    .get('wikipedia', hash);
  return row ? JSON.parse(row.response_json) : null;
}
function cacheSet(hash, data) {
  db.prepare('INSERT OR REPLACE INTO resource_cache (provider, request_hash, response_json) VALUES (?, ?, ?)')
    .run('wikipedia', hash, JSON.stringify(data));
}

/**
 * Resolve a "reading" excerpt for a topic.
 *   1. If the assignment has an uploaded textbook PDF, match the topic to the
 *      most relevant passage in it (keyless, best quality — it's their book).
 *   2. Otherwise fall back to a Wikipedia summary (free, keyless, reputable).
 */
export async function findReading(topic, assignmentId) {
  const t = (topic || '').trim();
  if (!t) return null;

  // 1. uploaded textbook PDF?
  const pdf = db.prepare(
    "SELECT * FROM attachment WHERE assignment_id = ? AND kind = 'uploaded_textbook' ORDER BY id DESC LIMIT 1"
  ).get(assignmentId);
  if (pdf) {
    const excerpt = await matchInPdf(pdf, t);
    if (excerpt) return excerpt;
  }

  // 2. Wikipedia fallback
  return await wikipediaExcerpt(t);
}

async function wikipediaExcerpt(topic) {
  const hash = createHash('sha256').update('wiki:' + topic).digest('hex');
  const cached = cacheGet(hash);
  if (cached) return { ...cached, cached: true };

  try {
    // Find the best-matching page title
    const sres = await fetch(`${WIKI_SEARCH}?q=${encodeURIComponent(topic)}&limit=1`, {
      headers: { 'User-Agent': 'learning++/0.1 (hackathon project)' },
    });
    if (!sres.ok) return readingFallback(topic, `wiki_search_${sres.status}`);
    const sdata = await sres.json();
    const page = sdata.pages?.[0];
    if (!page) return readingFallback(topic, 'wiki_no_page');

    // Get the page summary
    const sum = await fetch(`${WIKI_SUMMARY}/${encodeURIComponent(page.key)}`, {
      headers: { 'User-Agent': 'learning++/0.1 (hackathon project)' },
    });
    if (!sum.ok) return readingFallback(topic, `wiki_summary_${sum.status}`);
    const sdoc = await sum.json();

    const excerpt = {
      source: 'wikipedia',
      topic,
      heading: sdoc.title,
      text: sdoc.extract || '',
      url: sdoc.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${encodeURIComponent(page.key)}`,
      attachmentId: null,
      page: null,
      resolved: Boolean(sdoc.extract),
    };
    cacheSet(hash, excerpt);
    return { ...excerpt, cached: false };
  } catch (err) {
    return readingFallback(topic, 'wiki_error', err.message);
  }
}

// Naive-but-effective excerpt matcher: score each page/paragraph by overlap with
// the topic's keywords and return the best window. (A later step could use
// embeddings, but keyword overlap is fast, keyless, and demo-safe.)
async function matchInPdf(pdf, topic) {
  let pdfParse;
  try {
    pdfParse = (await import('pdf-parse')).default;
  } catch {
    return null; // pdf-parse not installed; fall through to Wikipedia
  }
  let text;
  try {
    const { readFileSync } = await import('node:fs');
    const buf = readFileSync(pdf.local_path);
    const parsed = await pdfParse(buf);
    text = parsed.text || '';
  } catch {
    return null;
  }
  if (!text.trim()) return null;

  const keywords = topic.toLowerCase().split(/\W+/).filter((w) => w.length > 3);
  const paras = text.split(/\n\s*\n/).map((p) => p.replace(/\s+/g, ' ').trim()).filter((p) => p.length > 80);

  let best = null, bestScore = 0;
  for (const para of paras) {
    const low = para.toLowerCase();
    const score = keywords.reduce((s, k) => s + (low.includes(k) ? 1 : 0), 0);
    if (score > bestScore) { bestScore = score; best = para; }
  }
  if (!best || bestScore === 0) return null;

  return {
    source: 'textbook',
    topic,
    heading: pdf.filename,
    text: best.slice(0, 1200),
    url: null,
    attachmentId: pdf.id,
    page: null,
    resolved: true,
  };
}

function readingFallback(topic, reason, detail) {
  return {
    source: 'none', topic, heading: null, text: '',
    url: `https://en.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(topic)}`,
    attachmentId: null, page: null, resolved: false, fallbackReason: reason, fallbackDetail: detail,
  };
}
