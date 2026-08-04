import { Hono } from "hono";
import { bearerFromAuthorization, sanitize, verifyBearerToken } from "@omi/platform";
import { defaultTenantRecord, ensureTenant, type TenantStore } from "@omi/tenant";

export type BffEnv = {
  ORIGIN_API_BASE: string;
  FIREBASE_PROJECT_ID: string;
  ADMIN_KEY?: string;
  ADMIN_KEY_AUTH_ENABLED?: string;
  TENANT_SHARD_COUNT?: string;
  TENANT_KV?: KVNamespace;
  ENCRYPTION_SECRET?: string;
};

type Variables = { uid: string };

const app = new Hono<{ Bindings: BffEnv; Variables: Variables }>();

app.get("/edge/health", (c) =>
  c.json({ ok: true, service: "omi-bff", ts: Date.now() }),
);

app.get("/edge/whoami", async (c) => {
  const token = bearerFromAuthorization(c.req.header("Authorization") ?? null);
  if (!token) return c.json({ error: "missing_authorization" }, 401);
  try {
    const uid = await verifyBearerToken(token, {
      FIREBASE_PROJECT_ID: c.env.FIREBASE_PROJECT_ID,
      ADMIN_KEY: c.env.ADMIN_KEY,
      ADMIN_KEY_AUTH_ENABLED: c.env.ADMIN_KEY_AUTH_ENABLED,
    });
    let tenant = null as ReturnType<typeof defaultTenantRecord> | null;
    if (c.env.TENANT_KV) {
      const store: TenantStore = {
        get: async (u) => {
          const raw = await c.env.TENANT_KV!.get(`tenant:${u}`, "json");
          return (raw as ReturnType<typeof defaultTenantRecord> | null) ?? null;
        },
        put: async (record) => {
          await c.env.TENANT_KV!.put(`tenant:${record.uid}`, JSON.stringify(record));
        },
      };
      const shardCount = Number(c.env.TENANT_SHARD_COUNT || "64");
      tenant = await ensureTenant(store, uid, { shardCount });
    } else {
      tenant = defaultTenantRecord(uid, {
        shardCount: Number(c.env.TENANT_SHARD_COUNT || "64"),
      });
    }
    return c.json({ uid, tenant });
  } catch (e) {
    return c.json({ error: "unauthorized", detail: sanitize(String(e)) }, 401);
  }
});

/** Default: reverse-proxy to Python Cloud Run origin (strangler). */
app.all("*", async (c) => {
  const base = (c.env.ORIGIN_API_BASE || "").replace(/\/$/, "");
  if (!base) return c.json({ error: "ORIGIN_API_BASE unset" }, 500);

  const url = new URL(c.req.url);
  const target = `${base}${url.pathname}${url.search}`;

  const headers = new Headers(c.req.raw.headers);
  headers.delete("host");
  headers.set("x-forwarded-host", url.host);
  headers.set("x-omi-edge", "bff");

  const init: RequestInit = {
    method: c.req.method,
    headers,
    redirect: "manual",
  };
  if (c.req.method !== "GET" && c.req.method !== "HEAD") {
    init.body = c.req.raw.body;
    // @ts-expect-error duplex required for streaming body in some runtimes
    init.duplex = "half";
  }

  const res = await fetch(target, init);
  const outHeaders = new Headers(res.headers);
  outHeaders.set("x-omi-edge", "bff");
  return new Response(res.body, { status: res.status, headers: outHeaders });
});

export default app;
