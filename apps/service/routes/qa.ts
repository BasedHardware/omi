// domain-pending(DIV-DOMCORE-001)
import type { Hono } from "hono";

import type { ServedCounter } from "../observability/served-count";

/**
 * QA control and observability routes.
 *
 * These exist so an unattended acceptance run - and a human watching a demo -
 * can tell whether the app is really hitting this backend or silently showing
 * its own fixtures. `/v1/qa/status` is the number an acceptance run asserts
 * nonzero against expected traffic.
 *
 * Nothing here returns user content. The status payload is counts and
 * configuration identity only, so it stays safe to poll, log, and paste.
 */

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });

export interface QaRouteDependencies {
  readonly counter: ServedCounter;
  /** Restores the seed to its initial deterministic state. Must be total. */
  readonly resetSeed: () => void;
  /** True when the supplied bearer token is the live dev token. */
  readonly isAuthorizedControlToken: (token: string) => boolean;
  /** Non-secret identity of the current seed, for display. */
  readonly seedIdentity: () => Readonly<Record<string, string | number>>;
}

const fixedResponse = (body: string, status: number): Response =>
  new Response(body, { status, headers: JSON_HEADERS });

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string") return null;
  const prefix = "Bearer ";
  if (!header.startsWith(prefix)) return null;
  const token = header.slice(prefix.length);
  return token.length > 0 ? token : null;
};

export const registerQaRoutes = (app: Hono, deps: QaRouteDependencies): void => {
  /**
   * Served-traffic observability. Deliberately unauthenticated: it carries no
   * user content, and requiring a token here would make the one thing that
   * detects a silently-fake demo harder to check than the demo itself.
   */
  app.get("/v1/qa/status", (context) => {
    deps.counter.recordNonDomainRequest();
    void context;
    return new Response(
      JSON.stringify({
        version: "qa-status-v1",
        served: deps.counter.snapshot(),
        seed: deps.seedIdentity(),
      }),
      { status: 200, headers: JSON_HEADERS },
    );
  });

  /** Total restore of the deterministic seed. Requires the dev token. */
  app.post("/v1/qa/reset", (context) => {
    deps.counter.recordNonDomainRequest();
    const token = bearerToken(context.req.header("authorization"));
    if (token === null || !deps.isAuthorizedControlToken(token)) {
      return fixedResponse(UNAUTHORIZED_BODY, 401);
    }
    try {
      deps.resetSeed();
    } catch {
      return fixedResponse(INTERNAL_BODY, 500);
    }
    return new Response(
      JSON.stringify({ version: "qa-reset-v1", status: "reset", seed: deps.seedIdentity() }),
      { status: 200, headers: JSON_HEADERS },
    );
  });
};
