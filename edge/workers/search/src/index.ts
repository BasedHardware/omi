import { Hono } from "hono";
import { bearerFromAuthorization, sanitize, verifyBearerToken } from "@omi/platform";
import { defaultTenantRecord } from "@omi/tenant";

export type SearchEnv = {
  FIREBASE_PROJECT_ID: string;
  ADMIN_KEY?: string;
  ADMIN_KEY_AUTH_ENABLED?: string;
  ORIGIN_API_BASE: string;
  TENANT_SHARD_COUNT?: string;
  /** Optional Vectorize binding when provisioned */
  MEMORY_VECTORS?: VectorizeIndex;
};

const app = new Hono<{ Bindings: SearchEnv }>();

app.get("/edge/search/health", (c) =>
  c.json({ ok: true, service: "omi-search", vectorize: Boolean(c.env.MEMORY_VECTORS) }),
);

/**
 * Semantic memory search.
 * Phase 1: if Vectorize unbound → proxy Python /v3/memories search.
 * Phase 2: query Vectorize filtered by uid + merge AI Search.
 */
app.get("/edge/search/memories", async (c) => {
  const token = bearerFromAuthorization(c.req.header("Authorization") ?? null);
  if (!token) return c.json({ error: "missing_authorization" }, 401);

  let uid: string;
  try {
    uid = await verifyBearerToken(token, {
      FIREBASE_PROJECT_ID: c.env.FIREBASE_PROJECT_ID,
      ADMIN_KEY: c.env.ADMIN_KEY,
      ADMIN_KEY_AUTH_ENABLED: c.env.ADMIN_KEY_AUTH_ENABLED,
    });
  } catch (e) {
    return c.json({ error: "unauthorized", detail: sanitize(String(e)) }, 401);
  }

  const q = c.req.query("q") || c.req.query("query") || "";
  if (!q) return c.json({ error: "q_required" }, 400);

  const tenant = defaultTenantRecord(uid, {
    shardCount: Number(c.env.TENANT_SHARD_COUNT || "64"),
  });

  if (!c.env.MEMORY_VECTORS) {
    const base = (c.env.ORIGIN_API_BASE || "").replace(/\/$/, "");
    const url = `${base}/v3/memories?limit=20&${new URLSearchParams({ search: q }).toString()}`;
    const res = await fetch(url, {
      headers: {
        Authorization: c.req.header("Authorization") || "",
        "x-omi-edge": "search-fallback",
      },
    });
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") || "application/json",
        "x-omi-edge": "search-origin-proxy",
        "x-omi-tenant-shard": tenant.d1DatabaseId,
      },
    });
  }

  // Vectorize path: caller must supply embedding via future AI binding; stub structure only.
  return c.json({
    uid,
    tenant,
    query: q,
    results: [],
    note: "vectorize_bound_embed_pipeline_todo",
  });
});

export default app;
