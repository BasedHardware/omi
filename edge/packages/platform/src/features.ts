/**
 * Feature gates for edge modules. Provider-agnostic: read from plain string map.
 * Cloudflare: wrangler [vars]. Node/Bun: process.env.
 *
 * EDGE_PROVIDER=cloudflare|node|bun — informational only
 * EDGE_MODULES=comma list or * — which Hono modules mount (default: health,whoami)
 * EDGE_PROXY_ORIGIN=true|false — reverse-proxy unknown routes to ORIGIN_API_BASE (default true)
 */

export type EdgeModuleId =
  | "health"
  | "whoami"
  | "memory"
  | "conversation"
  | "tasks"
  | "search"
  | "identity";

const ALL_MODULES: EdgeModuleId[] = [
  "health",
  "whoami",
  "memory",
  "conversation",
  "tasks",
  "search",
  "identity",
];

export type FeatureEnv = Record<string, string | undefined>;

function truthy(v: string | undefined, defaultValue: boolean): boolean {
  if (v === undefined || v === "") return defaultValue;
  const s = v.toLowerCase();
  if (["1", "true", "yes", "on"].includes(s)) return true;
  if (["0", "false", "no", "off"].includes(s)) return false;
  return defaultValue;
}

export function parseEdgeModules(raw: string | undefined): Set<EdgeModuleId> {
  if (!raw || raw.trim() === "") {
    return new Set<EdgeModuleId>(["health", "whoami"]);
  }
  if (raw.trim() === "*") {
    return new Set<EdgeModuleId>(ALL_MODULES);
  }
  const out = new Set<EdgeModuleId>();
  for (const part of raw.split(",")) {
    const id = part.trim().toLowerCase() as EdgeModuleId;
    if ((ALL_MODULES as string[]).includes(id)) out.add(id);
  }
  if (out.size === 0) {
    out.add("health");
    out.add("whoami");
  }
  return out;
}

export type EdgeFeatures = {
  provider: string;
  modules: Set<EdgeModuleId>;
  proxyOrigin: boolean;
  originApiBase: string;
  firebaseProjectId: string;
  adminKey?: string;
  adminKeyAuthEnabled: boolean;
  tenantShardCount: number;
  encryptionSecret?: string;
};

export function resolveFeatures(env: FeatureEnv): EdgeFeatures {
  return {
    provider: env.EDGE_PROVIDER || "unknown",
    modules: parseEdgeModules(env.EDGE_MODULES),
    proxyOrigin: truthy(env.EDGE_PROXY_ORIGIN, true),
    originApiBase: (env.ORIGIN_API_BASE || "").replace(/\/$/, ""),
    firebaseProjectId: env.FIREBASE_PROJECT_ID || "",
    adminKey: env.ADMIN_KEY,
    adminKeyAuthEnabled: truthy(env.ADMIN_KEY_AUTH_ENABLED, true),
    tenantShardCount: Number(env.TENANT_SHARD_COUNT || "64") || 64,
    encryptionSecret: env.ENCRYPTION_SECRET,
  };
}

export function moduleEnabled(features: EdgeFeatures, id: EdgeModuleId): boolean {
  return features.modules.has(id);
}
