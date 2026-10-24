import Fastify from 'fastify';
import cors from '@fastify/cors';
import fastifyStatic from '@fastify/static';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { initSchema } from './db/index.js';
import { registerRoutes } from './routes/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

initSchema();

const app = Fastify({ logger: true });

// CORS wide-open for the hackathon so the teammate's static page (any origin,
// including file://) can call the API. Tighten before anything real ships.
await app.register(cors, { origin: true });

// Serve the throwaway test harness at /  (SPEC §9)
await app.register(fastifyStatic, {
  root: join(__dirname, '..', 'public'),
  prefix: '/'
});

await app.register(registerRoutes);

const PORT = Number(process.env.PORT || 3000);
try {
  await app.listen({ port: PORT, host: '0.0.0.0' });
  console.log(`learning++ API on http://localhost:${PORT}  (test harness at /)`);
} catch (err) {
  app.log.error(err);
  process.exit(1);
}
