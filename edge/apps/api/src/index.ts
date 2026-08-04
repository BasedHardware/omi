/**
 * Cloudflare Workers adapter only.
 * Core app = @omi/gateway createApp (provider-agnostic Hono).
 * Feature gate: EDGE_MODULES + EDGE_PROXY_ORIGIN vars.
 */
import { createApp } from "@omi/gateway";
import { resolveFeatures, type AppDeps, type KvStore } from "@omi/platform";

export type WorkerEnv = {
  EDGE_PROVIDER?: string;
  EDGE_MODULES?: string;
  EDGE_PROXY_ORIGIN?: string;
  ORIGIN_API_BASE: string;
  FIREBASE_PROJECT_ID: string;
  ADMIN_KEY?: string;
  ADMIN_KEY_AUTH_ENABLED?: string;
  TENANT_SHARD_COUNT?: string;
  ENCRYPTION_SECRET?: string;
  /** Optional CF KV — only when bound */
  TENANT_KV?: {
    get(key: string, type?: "text" | "json"): Promise<string | unknown | null>;
    put(key: string, value: string): Promise<void>;
  };
};

function envMap(env: WorkerEnv): Record<string, string | undefined> {
  return {
    EDGE_PROVIDER: env.EDGE_PROVIDER || "cloudflare",
    EDGE_MODULES: env.EDGE_MODULES,
    EDGE_PROXY_ORIGIN: env.EDGE_PROXY_ORIGIN,
    ORIGIN_API_BASE: env.ORIGIN_API_BASE,
    FIREBASE_PROJECT_ID: env.FIREBASE_PROJECT_ID,
    ADMIN_KEY: env.ADMIN_KEY,
    ADMIN_KEY_AUTH_ENABLED: env.ADMIN_KEY_AUTH_ENABLED,
    TENANT_SHARD_COUNT: env.TENANT_SHARD_COUNT,
    ENCRYPTION_SECRET: env.ENCRYPTION_SECRET,
  };
}

function depsFromEnv(env: WorkerEnv): AppDeps {
  const features = resolveFeatures(envMap(env));
  let tenantKv: KvStore | undefined;
  if (env.TENANT_KV) {
    tenantKv = env.TENANT_KV;
  }
  return { features, tenantKv };
}

const worker = {
  async fetch(request: Request, env: WorkerEnv, _ctx: unknown): Promise<Response> {
    const app = createApp(depsFromEnv(env));
    return app.fetch(request);
  },
};

export default worker;
