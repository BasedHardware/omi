import { Hono } from "hono";
import { requireUid, sanitize, type AppDeps } from "@omi/platform";
import { originIdentityStore } from "./types.js";

export function identityRoutes(deps: AppDeps) {
  const app = new Hono<{ Variables: { uid: string; authHeader: string } }>();
  app.use("*", requireUid(deps.features));

  app.get("/profile", async (c) => {
    const store = originIdentityStore(deps.features.originApiBase, c.get("authHeader"));
    try {
      const profile = await store.getProfile(c.get("uid"));
      if (!profile) return c.json({ error: "not_found" }, 404);
      return c.json({ ...profile.raw, source: "origin" });
    } catch (e) {
      return c.json({ error: "profile_failed", detail: sanitize(String(e)) }, 502);
    }
  });

  return app;
}
