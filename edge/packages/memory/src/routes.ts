import { Hono } from "hono";
import {
  bearerFromAuthorization,
  sanitize,
  verifyBearerToken,
  type AppDeps,
} from "@omi/platform";
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
    const limit = queryInteger(c.req.query("limit"), 100);
    const offset = queryInteger(c.req.query("offset"), 0);
    if (limit === null || offset === null) return c.json({ error: "invalid_query" }, 422);
    try {
      const items = await store.list({
        uid,
        limit,
        offset,
        cursor: c.req.query("cursor") || undefined,
        deviceScope: c.req.query("device_scope") || undefined,
        clientDeviceId: c.req.query("client_device_id") || undefined,
      });
      return c.json(items);
    } catch (e) {
      return c.json({ error: "list_failed", detail: sanitize(String(e)) }, 502);
    }
  });

  return app;
}

function queryInteger(value: string | undefined, fallback: number): number | null {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}
