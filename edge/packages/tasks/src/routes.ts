import { Hono } from "hono";
import {
  bearerFromAuthorization,
  sanitize,
  verifyBearerToken,
  type AppDeps,
} from "@omi/platform";
import { originActionItemStore } from "./types.js";

export function tasksRoutes(deps: AppDeps) {
  const app = new Hono<{ Variables: { uid: string; authHeader: string } }>();

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
    const store = originActionItemStore(deps.features.originApiBase, c.get("authHeader"));
    try {
      const items = await store.list(c.get("uid"), Number(c.req.query("limit") || "50"));
      return c.json({ action_items: items, source: "origin" });
    } catch (e) {
      return c.json({ error: "list_failed", detail: sanitize(String(e)) }, 502);
    }
  });

  return app;
}
