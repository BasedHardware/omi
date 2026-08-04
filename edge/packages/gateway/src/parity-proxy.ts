import type { Hono } from "hono";
import { proxyToOrigin, type AppDeps } from "@omi/platform";

/**
 * Mount origin-transparent parity routes for a Python path prefix.
 * Edge adds x-omi-edge marker; body/query/method/auth pass through unchanged.
 * This is the parity baseline before a local store replaces origin.
 */
export function mountOriginParity(
  app: Hono,
  deps: AppDeps,
  opts: { prefix: string; edgeName: string },
): void {
  const base = deps.features.originApiBase;
  const handler = async (c: { req: { raw: Request } }) =>
    proxyToOrigin({
      originBase: base,
      request: c.req.raw,
      edgeName: opts.edgeName,
    });

  const p = opts.prefix.replace(/\/$/, "");
  app.all(p, handler);
  app.all(`${p}/*`, handler);
}
