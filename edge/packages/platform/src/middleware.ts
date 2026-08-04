import type { MiddlewareHandler } from "hono";
import { bearerFromAuthorization, verifyBearerToken, sanitize } from "./auth.js";
import type { EdgeFeatures } from "./features.js";

export type AuthVariables = {
  uid: string;
  authHeader: string;
  bearerToken: string;
};

/** Require Firebase / ADMIN_KEY bearer; sets uid on context. */
export function requireUid(features: EdgeFeatures): MiddlewareHandler<{ Variables: AuthVariables }> {
  return async (c, next) => {
    const header = c.req.header("Authorization") ?? null;
    const token = bearerFromAuthorization(header);
    if (!token) return c.json({ error: "missing_authorization" }, 401);
    try {
      const uid = await verifyBearerToken(token, {
        FIREBASE_PROJECT_ID: features.firebaseProjectId,
        ADMIN_KEY: features.adminKey,
        ADMIN_KEY_AUTH_ENABLED: String(features.adminKeyAuthEnabled),
      });
      c.set("uid", uid);
      c.set("authHeader", header || "");
      c.set("bearerToken", token);
      await next();
    } catch (e) {
      return c.json({ error: "unauthorized", detail: sanitize(String(e)) }, 401);
    }
  };
}
