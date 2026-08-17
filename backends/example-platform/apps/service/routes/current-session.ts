import type { Hono } from "hono";

import type { CurrentSessionPort, DevTokenResolver } from "../auth/current-session";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const EMPTY_HEADERS = Object.freeze({ "cache-control": "no-store" });
const UNAVAILABLE_HEADERS = Object.freeze({
  ...JSON_HEADERS,
  "retry-after": "60",
});

const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });
const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const UNAVAILABLE_BODY = JSON.stringify({ error: "service_unavailable" });

export const CURRENT_SESSION_PATH = "/v1/session/current";

export interface CurrentSessionRouteDependencies {
  readonly sessions: CurrentSessionPort;
  readonly resolveDevToken: DevTokenResolver;
}

const response = (
  body: string,
  status: number,
  headers: Readonly<Record<string, string>> = JSON_HEADERS,
): Response => new Response(body, { status, headers });

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const hasQuery = (request: Request): boolean => {
  try {
    return [...new URL(request.url).searchParams].length > 0;
  } catch {
    return true;
  }
};

/** Revokes only the presented service session; replay remains a bodyless 204. */
export const registerCurrentSessionRoutes = (
  app: Hono,
  deps: CurrentSessionRouteDependencies,
): void => {
  app.delete(CURRENT_SESSION_PATH, async (context) => {
    if (hasQuery(context.req.raw)) return response(BAD_REQUEST_BODY, 400);
    let body: string;
    try {
      body = await context.req.raw.text();
    } catch {
      return response(BAD_REQUEST_BODY, 400);
    }
    if (body.length > 0) return response(BAD_REQUEST_BODY, 400);

    const token = bearerToken(context.req.header("authorization"));
    if (token === null) return response(UNAUTHORIZED_BODY, 401);

    try {
      const result = deps.sessions.revoke(token, deps.resolveDevToken);
      if (result.status === "unrecognized") return response(UNAUTHORIZED_BODY, 401);
      return new Response(null, { status: 204, headers: EMPTY_HEADERS });
    } catch {
      return response(UNAVAILABLE_BODY, 503, UNAVAILABLE_HEADERS);
    }
  });
};
