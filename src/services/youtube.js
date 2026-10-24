import { createHash } from 'node:crypto';
import { db } from '../db/index.js';

const SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search';

function cacheGet(hash) {
  const row = db.prepare('SELECT response_json FROM resource_cache WHERE provider = ? AND request_hash = ?')
    .get('youtube', hash);
  return row ? JSON.parse(row.response_json) : null;
}
function cacheSet(hash, data) {
  db.prepare('INSERT OR REPLACE INTO resource_cache (provider, request_hash, response_json) VALUES (?, ?, ?)')
    .run('youtube', hash, JSON.stringify(data));
}

/**
 * Search YouTube for a teaching video. Returns a normalized video object, or a
 * keyless fallback (a search-page link) if no API key is set or the call fails.
 * Every successful result is cached by query (demo-safety §10).
 */
export async function findVideo(query) {
  const q = (query || '').trim();
  if (!q) return null;

  const hash = createHash('sha256').update('yt:' + q).digest('hex');
  const cached = cacheGet(hash);
  if (cached) return { ...cached, cached: true };

  const key = process.env.YOUTUBE_API_KEY;
  if (!key) return fallback(q, 'no_api_key');

  const url = `${SEARCH_URL}?part=snippet&type=video&videoEmbeddable=true&safeSearch=moderate&maxResults=3&q=${encodeURIComponent(q)}&key=${key}`;
  try {
    const res = await fetch(url);
    if (!res.ok) {
      const body = await res.text();
      // Quota exceeded (403) or other error -> graceful fallback, don't crash.
      return fallback(q, `http_${res.status}`, body.slice(0, 200));
    }
    const data = await res.json();
    const item = data.items?.[0];
    if (!item) return fallback(q, 'no_results');

    const video = {
      query: q,
      videoId: item.id.videoId,
      title: item.snippet.title,
      channel: item.snippet.channelTitle,
      durationSec: null, // search.list doesn't return duration; could add videos.list later
      url: `https://www.youtube.com/watch?v=${item.id.videoId}`,
      embedUrl: `https://www.youtube.com/embed/${item.id.videoId}`,
      thumbnail: item.snippet.thumbnails?.medium?.url || null,
      resolved: true,
    };
    cacheSet(hash, video);
    return { ...video, cached: false };
  } catch (err) {
    return fallback(q, 'fetch_error', err.message);
  }
}

function fallback(q, reason, detail) {
  return {
    query: q,
    videoId: null,
    title: `Search YouTube: "${q}"`,
    channel: null,
    durationSec: null,
    url: `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`,
    embedUrl: null,
    thumbnail: null,
    resolved: false,
    fallbackReason: reason,
    fallbackDetail: detail,
  };
}
