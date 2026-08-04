import { Hono } from "hono";
import {
  bearerFromAuthorization,
  moduleEnabled,
  proxyToOrigin,
  sanitize,
  verifyBearerToken,
  type AppDeps,
} from "@omi/platform";
import { defaultTenantRecord, ensureTenant, kvTenantStore } from "@omi/tenant";
import { memoryRoutes } from "@omi/memory";
import { conversationRoutes } from "@omi/conversation";
import { tasksRoutes } from "@omi/tasks";

/**
 * Provider-agnostic Hono app. Mount modules via EDGE_MODULES feature gate.
 * Cloudflare / Node / Bun only supply AppDeps + fetch.
 */
export function createApp(deps: AppDeps) {
  const app = new Hono();
  const f = deps.features;

  if (moduleEnabled(f, "health")) {
    app.get("/edge/health", (c) =>
      c.json({
        ok: true,
        service: "omi-edge",
        provider: f.provider,
        modules: [...f.modules].sort(),
        proxyOrigin: f.proxyOrigin,
        ts: Date.now(),
      }),
    );
  }

  if (moduleEnabled(f, "whoami")) {
    app.get("/edge/whoami", async (c) => {
      const token = bearerFromAuthorization(c.req.header("Authorization") ?? null);
      if (!token) return c.json({ error: "missing_authorization" }, 401);
      try {
        const uid = await verifyBearerToken(token, {
          FIREBASE_PROJECT_ID: f.firebaseProjectId,
          ADMIN_KEY: f.adminKey,
          ADMIN_KEY_AUTH_ENABLED: String(f.adminKeyAuthEnabled),
        });
        let tenant = defaultTenantRecord(uid, { shardCount: f.tenantShardCount });
        if (deps.tenantKv) {
          tenant = await ensureTenant(kvTenantStore(deps.tenantKv), uid, {
            shardCount: f.tenantShardCount,
          });
        }
        return c.json({ uid, tenant, provider: f.provider });
      } catch (e) {
        return c.json({ error: "unauthorized", detail: sanitize(String(e)) }, 401);
      }
    });
  }

  if (moduleEnabled(f, "memory")) {
    app.route("/edge/memories", memoryRoutes(deps));
  }

  if (moduleEnabled(f, "conversation")) {
    app.route("/edge/conversations", conversationRoutes(deps));
  }

  if (moduleEnabled(f, "tasks")) {
    app.route("/edge/tasks", tasksRoutes(deps));
  }

  if (moduleEnabled(f, "search")) {
    app.get("/edge/search/health", (c) =>
      c.json({
        ok: true,
        service: "omi-search",
        vector: Boolean(deps.memorySearch),
      }),
    );

    app.get("/edge/search/memories", async (c) => {
      const token = bearerFromAuthorization(c.req.header("Authorization") ?? null);
      if (!token) return c.json({ error: "missing_authorization" }, 401);
      let uid: string;
      try {
        uid = await verifyBearerToken(token, {
          FIREBASE_PROJECT_ID: f.firebaseProjectId,
          ADMIN_KEY: f.adminKey,
          ADMIN_KEY_AUTH_ENABLED: String(f.adminKeyAuthEnabled),
        });
      } catch (e) {
        return c.json({ error: "unauthorized", detail: sanitize(String(e)) }, 401);
      }
      const q = c.req.query("q") || c.req.query("query") || "";
      if (!q) return c.json({ error: "q_required" }, 400);
      const tenant = defaultTenantRecord(uid, { shardCount: f.tenantShardCount });

      if (deps.memorySearch) {
        const results = await deps.memorySearch.search({ uid, query: q, limit: 20 });
        return c.json({ uid, tenant, query: q, results, source: "vector" });
      }

      if (!f.originApiBase) return c.json({ error: "ORIGIN_API_BASE unset" }, 500);
      const url = `${f.originApiBase}/v3/memories?limit=20&${new URLSearchParams({ search: q })}`;
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
    });
  }

  if (f.proxyOrigin) {
    app.all("*", async (c) =>
      proxyToOrigin({
        originBase: f.originApiBase,
        request: c.req.raw,
        edgeName: "gateway-proxy",
      }),
    );
  } else {
    app.all("*", (c) => c.json({ error: "not_found", path: c.req.path }, 404));
  }

  return app;
}
