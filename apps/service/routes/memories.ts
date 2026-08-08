// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
import type { Hono } from "hono";

import { ApplicationReadDenied } from "../../../core/retrieve/authorization-boundary";
import type { DevPrincipal } from "../auth/dev-token";
import type { PreparedMemoryRead } from "../composition/memory-read";
import { readMemoryPage } from "../composition/memory-read";
import type { ServedCounter } from "../observability/served-count";

/**
 * The app-facing memory read routes.
 *
 * Response discipline, which is the security-relevant part of this file:
 *
 * - Every failure body is a FIXED constant. No denial reason, no exception
 *   message, no stack, no identifier ever reaches the wire or a log line. The
 *   authorization boundary distinguishes nine denial reasons internally; all
 *   nine produce one byte-identical 403 here, because telling a caller WHICH
 *   check failed is an oracle over grant state.
 * - A record hidden by authorization is filtered inside the projection, before
 *   rendering. It therefore produces the same page bytes as a record that never
 *   existed. This route must not reintroduce a difference through status codes,
 *   headers, or envelope shape - so the success path has exactly one shape
 *   regardless of how many records were hidden.
 * - Headers are identical on every response of a given class, including
 *   `cache-control`, so header presence cannot be used as a side channel.
 */

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

/** Fixed bodies. Never interpolate anything into these. */
const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const FORBIDDEN_BODY = JSON.stringify({ error: "forbidden" });
const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });

const DEFAULT_PAGE_LIMIT = 25;
const MAX_PAGE_LIMIT = 100;

export interface MemoryRouteDependencies {
  /** Resolves a bearer token to a principal, or null. Never throws for bad input. */
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  /** Builds the prepared read for one principal and one snapshot. */
  readonly prepareRead: (principal: DevPrincipal) => Promise<PreparedMemoryRead>;
  readonly counter: ServedCounter;
}

const fixedResponse = (body: string, status: number): Response =>
  new Response(body, { status, headers: JSON_HEADERS });

/** Extracts a bearer token without revealing which part of the header was wrong. */
const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string") return null;
  const prefix = "Bearer ";
  if (!header.startsWith(prefix)) return null;
  const token = header.slice(prefix.length);
  return token.length > 0 ? token : null;
};

/**
 * Parses the page request. `limit` and `cursor` are both optional: a client
 * that sends neither must still get a correct first page, because the ratified
 * contract makes cursor and status metadata optional for the consumer.
 */
const parsePageQuery = (
  rawLimit: string | undefined,
  rawCursor: string | undefined,
): { readonly limit: number; readonly cursor: string | null } | null => {
  let limit = DEFAULT_PAGE_LIMIT;
  if (rawLimit !== undefined) {
    if (!/^[0-9]{1,3}$/.test(rawLimit)) return null;
    limit = Number(rawLimit);
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_PAGE_LIMIT) return null;
  }
  const cursor = rawCursor === undefined || rawCursor.length === 0 ? null : rawCursor;
  return { limit, cursor };
};

export const registerMemoryRoutes = (app: Hono, deps: MemoryRouteDependencies): void => {
  // domain-pending(DIV-DOMCORE-001)
  app.get("/v1/memories", async (context) => {
    const token = bearerToken(context.req.header("authorization"));
    if (token === null) {
      deps.counter.recordDomainRead("denied");
      return fixedResponse(UNAUTHORIZED_BODY, 401);
    }
    const principal = deps.resolvePrincipal(token);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return fixedResponse(UNAUTHORIZED_BODY, 401);
    }

    const page = parsePageQuery(
      context.req.query("limit") ?? undefined,
      context.req.query("cursor") ?? undefined,
    );
    if (page === null) {
      deps.counter.recordDomainRead("denied");
      return fixedResponse(BAD_REQUEST_BODY, 400);
    }

    try {
      const prepared = await deps.prepareRead(principal);
      const result = await readMemoryPage({ limit: page.limit, cursor: page.cursor }, prepared);
      // Counted only here: after the domain response body actually exists.
      // Counting earlier is the wave-9 bug - a served count that moves when
      // nothing was served makes a stalled backend look healthy.
      deps.counter.recordDomainRead("served");
      return new Response(result.canonical_json, { status: 200, headers: JSON_HEADERS });
    } catch (error) {
      if (error instanceof ApplicationReadDenied) {
        // One body for all nine denial reasons. The reason is deliberately
        // dropped rather than logged: it describes grant state.
        deps.counter.recordDomainRead("denied");
        return fixedResponse(FORBIDDEN_BODY, 403);
      }
      // An invalid or replayed cursor is client-controlled and must not be
      // distinguishable by reason either.
      if (isInvalidCursor(error)) {
        deps.counter.recordDomainRead("denied");
        return fixedResponse(BAD_REQUEST_BODY, 400);
      }
      deps.counter.recordDomainRead("failed");
      return fixedResponse(INTERNAL_BODY, 500);
    }
  });
};

/**
 * Recognises the cursor module's single public failure shape without importing
 * its brand check across the app boundary. Every cursor failure - bad
 * signature, unknown key, expiry, replay against a different snapshot - carries
 * this one code, by design.
 */
const isInvalidCursor = (error: unknown): boolean =>
  typeof error === "object" && error !== null
  && (error as { code?: unknown }).code === "invalid_cursor";
