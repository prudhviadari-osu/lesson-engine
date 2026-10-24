import Database from 'better-sqlite3';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// DB file lives at the project root as learning.db (override with DB_PATH env)
const DB_PATH = process.env.DB_PATH || join(__dirname, '..', '..', 'learning.db');

export const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

/** Apply schema.sql — safe to run repeatedly (all CREATE ... IF NOT EXISTS). */
export function initSchema() {
  const schema = readFileSync(join(__dirname, 'schema.sql'), 'utf8');
  db.exec(schema);
}
