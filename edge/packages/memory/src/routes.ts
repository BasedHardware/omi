import { Hono } from "hono";
import {
  bearerFromAuthorization,
  sanitize,
  verifyBearerToken,
  type AppDeps,
} from "@omi/platform";
import { defaultTenantRecord } from "@omi/tenant";
import { originMemoryStore } from "./types.js";

export type MemoryRouteEnv = {
  Variables: { uid: string; authHeader: string };
};

export function memoryRoutes(deps: AppDeps) {
  const app = new Hono<MemoryRouteEnv>();

  app.use("*", async (c, next) => {
    const header = c.req.header("Authorization") ?? null;
    const token = bearerFromAuthorization(header);
    if (!token) return c.json({ error: "missing_authorization" }, 401);
    try {
      const uid = await verifyBearerToken(token, {
        FIREBASE_PROJECT_ID: deps.features.firebaseProjectId,
        ADMIN_KEY: deps.features.adminKey,
        ADMIN_KEY_AUTH_ENABLED: String(deps.features.adminKeyAuthEnabled),
      });
      c.set("uid", uid);
      c.set("authHeader", header || "");
      await next();
    } catch (e) {
      return c.json({ error: "unauthorized", detail: sanitize(String(e)) }, 401);
    }
  });

  app.get("/", async (c) => {
    const uid = c.get("uid");
    const store = originMemoryStore(deps.features.originApiBase, c.get("authHeader"));
    const limit = Number(c.req.query("limit") || "20");
    const search = c.req.query("search") || c.req.query("q") || undefined;
    const category = c.req.query("category") || undefined;
    try {
      const items = await store.list({ uid, limit, search, category });
      const tenant = defaultTenantRecord(uid, { shardCount: deps.features.tenantShardCount });
      return c.json({
        memories: items,
        tenant: { shard: tenant.d1DatabaseId },
        source: "origin",
      });
    } catch (e) {
      return c.json({ error: "list_failed", detail: sanitize(String(e)) }, 502);
    }
  });

  app.get("/:id", async (c) => {
    const uid = c.get("uid");
    const store = originMemoryStore(deps.features.originApiBase, c.get("authHeader"));
    try {
      const item = await store.get(uid, c.req.param("id"));
      if (!item) return c.json({ error: "not_found" }, 404);
      return c.json(item);
    } catch (e) {
      return c.json({ error: "get_failed", detail: sanitize(String(e)) }, 502);
    }
  });

  return app;
}
