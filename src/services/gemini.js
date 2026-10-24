import { GoogleGenAI } from '@google/genai';
import { createHash } from 'node:crypto';
import { db } from '../db/index.js';

const MODEL = process.env.GEMINI_MODEL || 'gemini-3.8-flash';

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

  const ai = getClient();
  const res = await ai.models.generateContent({
    model: MODEL,
    contents: prompt,
    config: {
      responseMimeType: 'application/json',
      responseSchema: schema,
    },
  });

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
