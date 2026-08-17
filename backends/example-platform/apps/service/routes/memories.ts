// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
import type { Hono } from "hono";
import { isProxy } from "node:util/types";

import {
  APP_CONTRACT_VERSION_HEADER,
  isWellFormedContractVersion,
  parseSynthesizedPageJson,
  resolveDeclaredContractVersion,
} from "@omi-core/ratified-contracts/projections/synthesized";

import { ApplicationReadDenied } from "../../../core/retrieve/authorization-boundary";
import type { DevPrincipal } from "../auth/dev-token";
import type { PreparedMemoryRead } from "../composition/memory-read";
import { readMemoryPage } from "../composition/memory-read";
import type { ServedCounter } from "../observability/served-count";
import {
  assertMemoryRouteReadPort,
  defineMemoryRouteReadPort,
  snapshotMemoryRouteReadOutcome,
  type MemoryRouteReadOutcome,
  type MemoryRouteReadPort,
} from "./memory-read-port";

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
  readonly readPort: MemoryRouteReadPort;
  readonly nowEpochSeconds: () => number;
  readonly counter: ServedCounter;
}

export interface PreparedMemoryRouteReadOptions {
  /** Resolves a bearer token to a principal, or null. Never throws for bad input. */
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  /** Builds the prepared read for one principal and one snapshot. */
  readonly prepareRead: (principal: DevPrincipal) => Promise<PreparedMemoryRead>;
}

/** Local/QA compatibility adapter; production supplies a PostgreSQL-backed port. */
export const createPreparedMemoryRouteReadPort = (
  options: PreparedMemoryRouteReadOptions,
): MemoryRouteReadPort => {
  if (options === null || typeof options !== "object" || Array.isArray(options)
    || isProxy(options) || Object.getPrototypeOf(options) !== Object.prototype) {
    throw new TypeError("invalid prepared memory route read options");
  }
  const descriptors = Object.getOwnPropertyDescriptors(options);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string")) {
    throw new TypeError("invalid prepared memory route read options");
  }
  const keys = (ownKeys as string[]).sort();
  if (keys.length !== 2 || keys[0] !== "prepareRead" || keys[1] !== "resolvePrincipal") {
    throw new TypeError("invalid prepared memory route read options");
  }
  const resolvePrincipal = descriptors.resolvePrincipal?.value;
  const prepareRead = descriptors.prepareRead?.value;
  if (!descriptors.resolvePrincipal?.enumerable || !descriptors.prepareRead?.enumerable
    || typeof resolvePrincipal !== "function" || isProxy(resolvePrincipal)
    || typeof prepareRead !== "function" || isProxy(prepareRead)) {
    throw new TypeError("invalid prepared memory route read options");
  }
  return defineMemoryRouteReadPort(
    async (input) => resolvePrincipal(input.bearer_token) !== null,
    async (input): Promise<MemoryRouteReadOutcome> => {
    const principal = resolvePrincipal(input.bearer_token);
    if (principal === null) return Object.freeze({ kind: "authentication_denied" });
    try {
      const prepared = await prepareRead(principal);
      const result = await readMemoryPage(input.request, prepared);
      return Object.freeze({ kind: "loaded", canonical_json: result.canonical_json });
    } catch (error) {
      if (error instanceof ApplicationReadDenied) {
        return Object.freeze({ kind: "authorization_denied" });
      }
      if (isInvalidCursor(error)) return Object.freeze({ kind: "invalid_cursor" });
      return Object.freeze({ kind: "unavailable" });
    }
    },
  );
};

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
  duplicated: boolean,
): { readonly limit: number; readonly cursor: string | null } | null => {
  // A repeated query parameter is ambiguous, and resolving it silently is a
  // parameter-pollution bug: Hono takes the FIRST value, so `?limit=5&limit=101`
  // was answered 200 while `?limit=101&limit=5` was answered 400. Two requests
  // carrying the same pair of values disagreed purely on ordering. Both grammars
  // here are single-valued, so ambiguity fails closed - the same rule
  // apps/mcp/bun-http.ts already applies to single-valued headers.
  if (duplicated) return null;

  let limit = DEFAULT_PAGE_LIMIT;
  if (rawLimit !== undefined) {
    if (!/^[0-9]{1,3}$/.test(rawLimit)) return null;
    limit = Number(rawLimit);
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_PAGE_LIMIT) return null;
  }
  const cursor = rawCursor === undefined || rawCursor.length === 0 ? null : rawCursor;
  return { limit, cursor };
};

/** True when any single-valued query parameter appears more than once. */
const hasDuplicateQueryParameters = (rawUrl: string): boolean => {
  let parameters: URLSearchParams;
  try {
    parameters = new URL(rawUrl).searchParams;
  } catch {
    return true;
  }
  for (const name of ["limit", "cursor"]) {
    if (parameters.getAll(name).length > 1) return true;
  }
  return false;
};

/**
 * The memory read path.
 *
 * CANONICAL: `GET /v1/memories`
 * TRANSITIONAL ALIAS: `GET /v1/memories/recall`
 *
 * The endpoint path is not part of ratified 0.1.1 - the contract fixes the wire
 * SHAPE, not the URL - so the spelling was an open choice. `/v1/memories` wins
 * because this is a paginated collection read with no query input: it takes
 * `limit` and `cursor` and nothing else. `/recall` reads as a verb, which would
 * misdescribe a plain list, and it is worth keeping free for the day a genuinely
 * query-bearing recall is ratified - that endpoint will want exactly this name.
 *
 * The alias exists only because FE-CORE had already integrated against
 * `/v1/memories/recall` before the spelling was settled. It routes to the same
 * handler and returns byte-identical responses. It is a dated migration shim,
 * not a second supported name: delete it once FE-CORE and FE-SHELLS point at
 * the canonical path.
 */
// domain-pending(DIV-DOMCORE-001)
export const MEMORY_READ_PATH = "/v1/memories";
// domain-pending(DIV-DOMCORE-001)
export const MEMORY_READ_TRANSITIONAL_ALIAS_PATH = "/v1/memories/recall";

export const registerMemoryRoutes = (app: Hono, deps: MemoryRouteDependencies): void => {
  if (deps === null || typeof deps !== "object" || Array.isArray(deps) || isProxy(deps)
    || Object.getPrototypeOf(deps) !== Object.prototype) {
    throw new TypeError("invalid memory route dependencies");
  }
  const descriptors = Object.getOwnPropertyDescriptors(deps);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string")) {
    throw new TypeError("invalid memory route dependencies");
  }
  const keys = (ownKeys as string[]).sort();
  if (keys.length !== 3 || keys[0] !== "counter" || keys[1] !== "nowEpochSeconds"
    || keys[2] !== "readPort" || Object.values(descriptors).some((entry) =>
      !entry.enumerable || !("value" in entry))) {
    throw new TypeError("invalid memory route dependencies");
  }
  const readPort = assertMemoryRouteReadPort(descriptors.readPort!.value as MemoryRouteReadPort);
  const authenticate = readPort.authenticate;
  const read = readPort.read;
  const nowEpochSeconds = descriptors.nowEpochSeconds!.value;
  const counter = descriptors.counter!.value as ServedCounter;
  if (typeof nowEpochSeconds !== "function" || isProxy(nowEpochSeconds)
    || counter === null || typeof counter !== "object" || isProxy(counter)) {
    throw new TypeError("memory route requires a clock");
  }
  const counterDescriptors = Object.getOwnPropertyDescriptors(counter);
  const recordDomainReadValue = counterDescriptors.recordDomainRead?.value;
  const recordDeclaredContractVersionValue = counterDescriptors.recordDeclaredContractVersion?.value;
  if (typeof recordDomainReadValue !== "function" || isProxy(recordDomainReadValue)
    || typeof recordDeclaredContractVersionValue !== "function"
    || isProxy(recordDeclaredContractVersionValue)) {
    throw new TypeError("memory route requires a served counter");
  }
  const recordDomainRead = recordDomainReadValue.bind(counter) as ServedCounter["recordDomainRead"];
  const recordDeclaredContractVersion = recordDeclaredContractVersionValue.bind(counter) as
    ServedCounter["recordDeclaredContractVersion"];
  // domain-pending(DIV-DOMCORE-001)
  const handler = async (context: {
    req: {
      url: string;
      header: (name: string) => string | undefined;
      query: (name: string) => string | undefined;
    };
  }): Promise<Response> => {
    const token = bearerToken(context.req.header("authorization"));
    if (token === null) {
      recordDomainRead("denied");
      return fixedResponse(UNAUTHORIZED_BODY, 401);
    }
    const declaredContractVersionHeader = context.req.header(APP_CONTRACT_VERSION_HEADER);
    const recordContractVersion = (): void => {
      // Authentication still precedes request validation. Consequently an
      // unauthenticated request cannot affect declared-version population
      // statistics or learn whether its query was valid.
      recordDeclaredContractVersion({
        atFloor: typeof declaredContractVersionHeader !== "string"
          || !isWellFormedContractVersion(declaredContractVersionHeader.trim()),
      });
      void resolveDeclaredContractVersion(declaredContractVersionHeader);
    };

    const page = parsePageQuery(
      context.req.query("limit") ?? undefined,
      context.req.query("cursor") ?? undefined,
      hasDuplicateQueryParameters(context.req.url),
    );
    if (page === null) {
      try {
        const now = nowEpochSeconds();
        if (!Number.isSafeInteger(now) || now < 0) throw new TypeError("invalid route clock");
        if (await authenticate({ bearer_token: token, now_epoch_seconds: now }) !== true) {
          recordDomainRead("denied");
          return fixedResponse(UNAUTHORIZED_BODY, 401);
        }
        recordContractVersion();
        recordDomainRead("denied");
        return fixedResponse(BAD_REQUEST_BODY, 400);
      } catch {
        recordDomainRead("failed");
        return fixedResponse(INTERNAL_BODY, 500);
      }
    }

    try {
      const now = nowEpochSeconds();
      if (!Number.isSafeInteger(now) || now < 0) throw new TypeError("invalid route clock");
      const outcome = snapshotMemoryRouteReadOutcome(await read({
        bearer_token: token,
        now_epoch_seconds: now,
        request: Object.freeze({ limit: page.limit, cursor: page.cursor }),
      }));
      if (outcome === null) {
        recordDomainRead("failed");
        return fixedResponse(INTERNAL_BODY, 500);
      }
      if (outcome.kind === "authentication_denied") {
        recordDomainRead("denied");
        return fixedResponse(UNAUTHORIZED_BODY, 401);
      }
      recordContractVersion();
      if (outcome.kind === "authorization_denied") {
        recordDomainRead("denied");
        return fixedResponse(FORBIDDEN_BODY, 403);
      }
      if (outcome.kind === "invalid_cursor") {
        recordDomainRead("denied");
        return fixedResponse(BAD_REQUEST_BODY, 400);
      }
      if (outcome.kind !== "loaded" || parseSynthesizedPageJson(outcome.canonical_json) === null) {
        recordDomainRead("failed");
        return fixedResponse(INTERNAL_BODY, 500);
      }
      // Counted only here: after the domain response body actually exists.
      // Counting earlier is the wave-9 bug - a served count that moves when
      // nothing was served makes a stalled backend look healthy.
      recordDomainRead("served");
      return new Response(outcome.canonical_json, { status: 200, headers: JSON_HEADERS });
    } catch {
      recordDomainRead("failed");
      return fixedResponse(INTERNAL_BODY, 500);
    }
  };

  // Both paths share one handler, so the alias cannot drift from the canonical
  // route's bytes, status codes, headers, or served-count accounting.
  app.get(MEMORY_READ_PATH, handler);
  app.get(MEMORY_READ_TRANSITIONAL_ALIAS_PATH, handler);
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
