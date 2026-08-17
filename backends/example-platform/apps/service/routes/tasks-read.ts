/**
 * The app-facing tasks READ route.
 *
 * Response discipline, which is the security-relevant part of this file, and it
 * is deliberately the SAME discipline as `routes/memories.ts` rather than a
 * second interpretation of it:
 *
 * - Every failure body is a FIXED constant. No denial reason, no exception
 *   message, no stack, no identifier ever reaches the wire or a log line.
 * - A record hidden by authorization is filtered before projection, so it
 *   produces the same page bytes as a record that never existed. This route
 *   must not reintroduce a difference through status codes, headers, or
 *   envelope shape.
 * - Headers are identical on every response of a given class, including
 *   `cache-control`, so header presence cannot be used as a side channel.
 * - **Refusals are byte-identical to an unknown route, and epoch-free** (R10).
 *   The tasks read is the surface the account epoch will ride on (D3, CLIENT's
 *   bump), which makes it exactly the surface where an epoch must never appear
 *   in a refusal: W1's condition is that the value is never served to a caller
 *   without authority over the account, and a refusal is by definition such a
 *   caller. `tasks-read.test.ts` asserts the bytes rather than trusting this.
 *
 * WHY THE HARDENING IS COPIED RATHER THAN SHARED. `parsePageQuery` and the
 * duplicate-parameter check look like extractable helpers, and extracting them
 * was considered and rejected: the memories route's grammar is `limit` +
 * `cursor` today and the two routes' grammars are free to diverge the moment
 * either wire gains a parameter. A shared parser would make that divergence a
 * silent behaviour change in the OTHER route — the two-doors defect wearing a
 * helper's clothes. What IS shared is the thing that must never differ: the
 * fixed refusal bodies, asserted equal across both routes by test.
 */

import type { Hono } from "hono";

import {
  APP_CONTRACT_VERSION_HEADER,
  isWellFormedContractVersion,
  resolveDeclaredContractVersion,
} from "@omi-core/ratified-contracts/projections/synthesized";

import { ApplicationReadDenied } from "../../../core/retrieve/authorization-boundary";
import type { DevPrincipal } from "../auth/dev-token";
import type { PreparedTasksRead } from "../composition/tasks-read";
import { UnprojectableTaskRecordError, readTasksPage } from "../composition/tasks-read";
import type { AccountControlProjectionStore } from "../control/projection-store";
import type { ServedCounter } from "../observability/served-count";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

/**
 * Fixed bodies. Never interpolate anything into these, and never add a field.
 *
 * These are the SAME byte strings `routes/memories.ts` uses and the same one
 * `app-facing.ts`'s `notFound` uses. That is the property R10 makes
 * load-bearing for this route in particular: a refusal here must be
 * indistinguishable from a refusal at a route that does not exist, or the
 * refusal itself becomes an account-existence oracle.
 */
const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const FORBIDDEN_BODY = JSON.stringify({ error: "forbidden" });
const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });

const DEFAULT_PAGE_LIMIT = 25;
const MAX_PAGE_LIMIT = 100;

export interface TasksReadRouteDependencies {
  /** Resolves a bearer token to a principal, or null. Never throws for bad input. */
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  /** Builds the prepared read for one principal. */
  readonly prepareRead: (principal: DevPrincipal) => PreparedTasksRead;
  /** The write fence's existing per-account projection store. */
  readonly fence: {
    readonly store: AccountControlProjectionStore;
  };
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
 * A repeated query parameter is ambiguous, and resolving it silently is a
 * parameter-pollution bug: Hono takes the FIRST value, so `?limit=5&limit=101`
 * was answered 200 on the memories route while `?limit=101&limit=5` was answered
 * 400 — two requests carrying the same pair of values disagreeing purely on
 * ordering. Both grammars here are single-valued, so ambiguity fails closed.
 */
const parsePageQuery = (
  rawLimit: string | undefined,
  rawCursor: string | undefined,
  duplicated: boolean,
): { readonly limit: number; readonly cursor: string | null } | null => {
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
 * `GET /v1/tasks`.
 *
 * A noun, and no transitional alias. The memories route carries
 * `/v1/memories/recall` only because a consumer had integrated against it
 * before the spelling settled; nothing has integrated against this one yet, so
 * it ships with exactly one name. A second name is a second thing to keep
 * byte-identical forever.
 */
export const TASKS_READ_PATH = "/v1/tasks";

export const registerTasksReadRoutes = (app: Hono, deps: TasksReadRouteDependencies): void => {
  const handler = async (context: {
    req: {
      url: string;
      header: (name: string) => string | undefined;
      query: (name: string) => string | undefined;
    };
  }): Promise<Response> => {
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

    // COORD-contract-evolution-policy §4: every app-facing request declares the
    // contract version its client was built against; absent is treated as the
    // floor. Read only — it does not gate or alter the response.
    const declaredContractVersionHeader = context.req.header(APP_CONTRACT_VERSION_HEADER);
    deps.counter.recordDeclaredContractVersion({
      atFloor: typeof declaredContractVersionHeader !== "string"
        || !isWellFormedContractVersion(declaredContractVersionHeader.trim()),
    });
    void resolveDeclaredContractVersion(declaredContractVersionHeader);

    const page = parsePageQuery(
      context.req.query("limit") ?? undefined,
      context.req.query("cursor") ?? undefined,
      hasDuplicateQueryParameters(context.req.url),
    );
    if (page === null) {
      deps.counter.recordDomainRead("denied");
      return fixedResponse(BAD_REQUEST_BODY, 400);
    }

    try {
      const prepared = deps.prepareRead(principal);
      const result = readTasksPage({ limit: page.limit, cursor: page.cursor }, prepared);
      const projection = deps.fence.store.read(principal.uid);
      const accountEpoch = projection === null ? null : projection.account_epoch;
      // Presence, never truthiness: epoch 0 is a real epoch, while an absent
      // projection (or one with no asserted epoch) preserves the optional 0.6.0
      // key set instead of fabricating generation zero.
      const body = accountEpoch === null
        ? result.canonical_json
        : JSON.stringify({
            ...(JSON.parse(result.canonical_json) as Record<string, unknown>),
            accountEpoch,
          });
      // Counted only here: after the domain response body actually exists.
      // Counting earlier is the wave-9 bug — a served count that moves when
      // nothing was served makes a stalled backend look healthy.
      deps.counter.recordDomainRead("served");
      return new Response(body, { status: 200, headers: JSON_HEADERS });
    } catch (error) {
      if (error instanceof ApplicationReadDenied) {
        // Match the memories read: every internal authorization denial collapses
        // onto one fixed body, with no account or epoch material interpolated.
        deps.counter.recordDomainRead("denied");
        return fixedResponse(FORBIDDEN_BODY, 403);
      }
      // A record whose opaque bag does not satisfy the ratified read model is a
      // SERVER fault, not a client-controlled one, and it answers 500 — never
      // 400, and never a short page. Answering 400 would let a caller learn
      // something about stored state from a request it controls; serving a page
      // with the record silently omitted would be a short page that looks
      // complete, which is the whole thing the completeness envelope exists to
      // prevent.
      if (error instanceof UnprojectableTaskRecordError) {
        deps.counter.recordDomainRead("failed");
        return fixedResponse(INTERNAL_BODY, 500);
      }
      // An invalid or replayed cursor is client-controlled and must not be
      // distinguishable by reason.
      if (isInvalidCursor(error)) {
        deps.counter.recordDomainRead("denied");
        return fixedResponse(BAD_REQUEST_BODY, 400);
      }
      deps.counter.recordDomainRead("failed");
      return fixedResponse(INTERNAL_BODY, 500);
    }
  };

  app.get(TASKS_READ_PATH, handler);
};

/**
 * Recognises the cursor module's single public failure shape without importing
 * its brand check across the app boundary. Every cursor failure — bad signature,
 * unknown key, expiry, replay against a different snapshot — carries this one
 * code, by design.
 */
const isInvalidCursor = (error: unknown): boolean =>
  typeof error === "object" && error !== null
  && (error as { code?: unknown }).code === "invalid_cursor";
