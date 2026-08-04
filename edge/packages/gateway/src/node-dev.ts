/**
 * Local Bun/Node serve — no Cloudflare.
 *   bun run packages/gateway/src/node-dev.ts
 */
import { createApp } from "./create-app.js";
import { resolveFeatures, memoryKv } from "@omi/platform";

const env = {
  EDGE_PROVIDER: process.env.EDGE_PROVIDER || "bun",
  EDGE_MODULES: process.env.EDGE_MODULES || "health,whoami,memory,conversation,tasks,search",
  EDGE_PROXY_ORIGIN: process.env.EDGE_PROXY_ORIGIN || "true",
  ORIGIN_API_BASE: process.env.ORIGIN_API_BASE || "http://127.0.0.1:8080",
  FIREBASE_PROJECT_ID: process.env.FIREBASE_PROJECT_ID || "based-hardware",
  ADMIN_KEY: process.env.ADMIN_KEY,
  ADMIN_KEY_AUTH_ENABLED: process.env.ADMIN_KEY_AUTH_ENABLED,
  TENANT_SHARD_COUNT: process.env.TENANT_SHARD_COUNT || "64",
  ENCRYPTION_SECRET: process.env.ENCRYPTION_SECRET,
};

const app = createApp({
  features: resolveFeatures(env),
  tenantKv: memoryKv(),
});

const port = Number(process.env.PORT || "8787");
console.log(`omi-edge listening :${port} modules=${env.EDGE_MODULES}`);

export default {
  port,
  fetch: app.fetch,
};
