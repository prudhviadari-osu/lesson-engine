import { GoogleGenAI } from '@google/genai';
import { createHash } from 'node:crypto';
import { db } from '../db/index.js';

// Primary model + automatic fallbacks when the primary is overloaded (503) or
// rate-limited (429). Lighter models generally have more free-tier headroom.
const PRIMARY_MODEL = process.env.GEMINI_MODEL || 'gemini-3.8-flash';
const FALLBACK_MODELS = (process.env.GEMINI_FALLBACKS || 'gemini-3.1-flash-lite,gemini-3.1-flash')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);
const MODEL_CHAIN = [PRIMARY_MODEL, ...FALLBACK_MODELS.filter((m) => m !== PRIMARY_MODEL)];

const MAX_RETRIES = 3;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function isTransient(err) {
  const s = err?.status ?? err?.code;
  const msg = String(err?.message || '').toLowerCase();
  return (
    s === 503 || s === 429 || s === 500 ||
    msg.includes('overload') || msg.includes('high demand') ||
    msg.includes('unavailable') || msg.includes('rate') || msg.includes('quota') ||
    msg.includes('resource_exhausted')
  );
}

let client = null;
function getClient() {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    const err = new Error('GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.');
    err.code = 'NO_API_KEY';
    throw err;
  }
  if (!client) client = new GoogleGenAI({ apiKey: key });
  return client;
}

function hashRequest(parts) {
  return createHash('sha256').update(JSON.stringify(parts)).digest('hex');
}

// Try the model chain; within each model, retry transient errors with backoff.
async function callWithFallback({ prompt, schema }) {
  const ai = getClient();
  let lastErr;
  for (const model of MODEL_CHAIN) {
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      try {
        const res = await ai.models.generateContent({
          model,
          contents: prompt,
          config: { responseMimeType: 'application/json', responseSchema: schema },
        });
        return { res, modelUsed: model };
      } catch (err) {
        lastErr = err;
        if (isTransient(err) && attempt < MAX_RETRIES) {
          await sleep(attempt * 1500); // 1.5s, 3s backoff
          continue;
        }
        if (isTransient(err)) break; // exhausted retries on this model -> next model
        throw err; // non-transient (bad key, bad request): fail immediately
      }
    }
  }
  const err = new Error(
    `All Gemini models overloaded/unavailable (tried: ${MODEL_CHAIN.join(', ')}). ` +
    `This is a free-tier "high demand" issue — wait a bit and retry, or set GEMINI_MODEL to a lighter model.`
  );
  err.code = 'OVERLOADED';
  err.cause = lastErr;
  throw err;
}

/**
 * Call Gemini with a prompt + responseSchema, returning parsed JSON.
 * Caches every successful response in resource_cache keyed by input hash
 * (SPEC §10 demo-safety): if the live call fails later, we can serve cache.
 */
export async function generateJSON({ prompt, schema, cacheKeyExtra = '' }) {
  const request_hash = hashRequest({ model: MODEL, prompt, schema, cacheKeyExtra });

  // Cache hit?
  const cached = db
    .prepare('SELECT response_json FROM resource_cache WHERE provider = ? AND request_hash = ?')
    .get('gemini', request_hash);
  if (cached) {
    return { data: JSON.parse(cached.response_json), cached: true };
  }

  const { res, modelUsed } = await callWithFallback({ prompt, schema });

  const text = res.text;
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    const err = new Error('Gemini returned non-JSON despite responseSchema.');
    err.raw = text;
    throw err;
  }

  db.prepare(
    'INSERT OR REPLACE INTO resource_cache (provider, request_hash, response_json) VALUES (?, ?, ?)'
  ).run('gemini', request_hash, JSON.stringify(data));

  return { data, cached: false };
}
