// domain-pending(DIV-DOMCORE-013)
// domain-pending(UNK-DOMCORE-002)
import type { Hono } from "hono";

import {
  APP_CONTRACT_VERSION_HEADER,
  isWellFormedContractVersion,
  resolveDeclaredContractVersion,
} from "@omi-core/ratified-contracts/projections/synthesized";

import type { DevPrincipal } from "../auth/dev-token";
import type { PreparedConversationsRead } from "../composition/conversations-read";
import {
  UnprojectableConversationRecordError,
  readConversationsPage,
} from "../composition/conversations-read";
import type { ServedCounter } from "../observability/served-count";
import type {
  ConversationPatchOutcome,
  ConversationsStore,
  ConversationVisibility,
} from "../stores/conversations-store";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json; charset=utf-8",
});
const ENVELOPE_JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const EMPTY_HEADERS = Object.freeze({ "cache-control": "no-store" });

const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });

export const CONVERSATIONS_PATH = "/v1/conversations";
const CONVERSATION_PREFIX = `${CONVERSATIONS_PATH}/`;
const DEFAULT_LIMIT = 500;
const MAX_LIMIT = 5_000;
const DEFAULT_PAGE_LIMIT = 25;
const MAX_PAGE_LIMIT = 100;

export interface ConversationRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly store: ConversationsStore;
  readonly counter: ServedCounter;
  /** The composition root owns the clock. QA uses the prototype's fixed instant. */
  readonly now: () => string;
  /** Builds the prepared ratified read for one principal. */
  readonly prepareRead: (principal: DevPrincipal) => PreparedConversationsRead;
}

const jsonResponse = (value: unknown, status = 200): Response =>
  new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });

const errorResponse = (status: number, code: string): Response =>
  jsonResponse({ error: code }, status);

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const authenticate = (
  header: string | undefined,
  resolvePrincipal: ConversationRouteDependencies["resolvePrincipal"],
): DevPrincipal | null => {
  const token = bearerToken(header);
  return token === null ? null : resolvePrincipal(token);
};

/** Mirrors the prototype's parseInt/fallback/clamp behavior exactly. */
const parseLimit = (value: string | null, fallback: number): number => {
  const parsed = Number.parseInt(value ?? "", 10);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return Math.min(parsed, MAX_LIMIT);
};

const decodeId = (raw: string): string | null => {
  if (!raw || raw.includes("/")) return null;
  try {
    const decoded = decodeURIComponent(raw);
    return decoded && !decoded.includes("/") ? decoded : null;
  } catch {
    return null;
  }
};

const requestUrl = (raw: Request): URL | null => {
  try {
    return new URL(raw.url);
  } catch {
    return null;
  }
};

const patchResponse = (outcome: ConversationPatchOutcome): Response => {
  if (!outcome.updated) {
    return errorResponse(
      404,
      outcome.reason === "folder_not_found" ? "folder_not_found" : "not_found",
    );
  }
  return jsonResponse(outcome.record);
};

const readJsonLikePrototype = async (request: Request): Promise<unknown> => {
  const body = await request.text();
  if (body.length === 0) return {};
  return JSON.parse(body) as unknown;
};

export const registerConversationRoutes = (
  app: Hono,
  deps: ConversationRouteDependencies,
): void => {
  app.get(CONVERSATIONS_PATH, (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    const url = requestUrl(context.req.raw);
    if (url === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(400, "invalid_url");
    }
    // Dual-serve: `offset` present keeps the legacy bare array so Home and
    // adapters-legacy keep working until the next lane deletes them. Absence
    // of `offset` is the ratified envelope (`limit`/`cursor`).
    if (url.searchParams.has("offset")) {
      const limit = parseLimit(url.searchParams.get("limit"), DEFAULT_LIMIT);
      const offset = parseLimit(url.searchParams.get("offset"), 0);
      const records = deps.store.listRecords(principal.uid);
      deps.counter.recordDomainRead("served");
      return jsonResponse(records.slice(offset, offset + limit));
    }
    return serveConversationsEnvelope(context.req.raw, principal, deps);
  });

  app.patch(`${CONVERSATIONS_PATH}/*`, async (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) return errorResponse(401, "unauthorized");
    const url = requestUrl(context.req.raw);
    if (url === null) return errorResponse(400, "invalid_url");

    try {
      const remainder = url.pathname.slice(CONVERSATION_PREFIX.length);
      const slash = remainder.indexOf("/");
      if (slash < 1 || remainder.slice(slash + 1).includes("/")) {
        return errorResponse(404, "not_found");
      }
      const id = decodeId(remainder.slice(0, slash));
      if (id === null) return errorResponse(404, "not_found");
      const field = remainder.slice(slash + 1);
      if (deps.store.readRecord(principal.uid, id) === null) {
        return errorResponse(404, "not_found");
      }

      if (field === "title") {
        const title = url.searchParams.get("title");
        if (title === null) return errorResponse(400, "title_required");
        return patchResponse(deps.store.updateTitle(principal.uid, id, title, deps.now()));
      }
      if (field === "starred") {
        const starred = url.searchParams.get("starred");
        if (starred !== "true" && starred !== "false") {
          return errorResponse(400, "starred_required");
        }
        return patchResponse(
          deps.store.updateStarred(principal.uid, id, starred === "true", deps.now()),
        );
      }
      if (field === "visibility") {
        const visibility = url.searchParams.get("value");
        if (visibility !== "public" && visibility !== "private" && visibility !== "shared") {
          return errorResponse(400, "invalid_visibility");
        }
        return patchResponse(deps.store.updateVisibility(
          principal.uid,
          id,
          visibility as ConversationVisibility,
          deps.now(),
        ));
      }
      if (field === "folder") {
        let body: unknown;
        try {
          body = await readJsonLikePrototype(context.req.raw);
        } catch {
          return errorResponse(400, "invalid_json");
        }
        // Intended wire: a missing or non-object body is `folder_id_required`,
        // never the prototype's `Object.hasOwn(null)` → 500 `qa_server_error`.
        if (body === null || typeof body !== "object" || Array.isArray(body)) {
          return errorResponse(400, "folder_id_required");
        }
        if (!Object.hasOwn(body, "folder_id")) {
          return errorResponse(400, "folder_id_required");
        }
        const folderId = (body as { readonly folder_id: unknown }).folder_id;
        if (folderId !== null && typeof folderId !== "string") {
          return errorResponse(400, "folder_id_invalid");
        }
        return patchResponse(deps.store.updateFolder(
          principal.uid,
          id,
          folderId,
          deps.now(),
        ));
      }
      return errorResponse(404, "not_found");
    } catch {
      return errorResponse(500, "qa_server_error");
    }
  });

  app.delete(`${CONVERSATIONS_PATH}/*`, (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) return errorResponse(401, "unauthorized");
    const url = requestUrl(context.req.raw);
    if (url === null) return errorResponse(400, "invalid_url");
    if (url.searchParams.get("cascade") !== "false") {
      return errorResponse(400, "cascade_required");
    }
    const id = decodeId(url.pathname.slice(CONVERSATION_PREFIX.length));
    if (id === null) return errorResponse(404, "not_found");
    const outcome = deps.store.deleteRecord(principal.uid, id);
    if (!outcome.deleted) return errorResponse(404, "not_found");
    return new Response(null, { status: 204, headers: EMPTY_HEADERS });
  });
};

const parseEnvelopeQuery = (
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

const serveConversationsEnvelope = (
  request: Request,
  principal: DevPrincipal,
  deps: ConversationRouteDependencies,
): Response => {
  const declaredContractVersionHeader = request.headers.get(APP_CONTRACT_VERSION_HEADER) ?? undefined;
  deps.counter.recordDeclaredContractVersion({
    atFloor: typeof declaredContractVersionHeader !== "string"
      || !isWellFormedContractVersion(declaredContractVersionHeader.trim()),
  });
  void resolveDeclaredContractVersion(declaredContractVersionHeader);

  const url = new URL(request.url);
  const page = parseEnvelopeQuery(
    url.searchParams.get("limit") ?? undefined,
    url.searchParams.get("cursor") ?? undefined,
    hasDuplicateQueryParameters(request.url),
  );
  if (page === null) {
    deps.counter.recordDomainRead("denied");
    return new Response(BAD_REQUEST_BODY, { status: 400, headers: ENVELOPE_JSON_HEADERS });
  }

  try {
    const prepared = deps.prepareRead(principal);
    const result = readConversationsPage({ limit: page.limit, cursor: page.cursor }, prepared);
    deps.counter.recordDomainRead("served");
    return new Response(result.canonical_json, { status: 200, headers: ENVELOPE_JSON_HEADERS });
  } catch (error) {
    if (error instanceof UnprojectableConversationRecordError) {
      deps.counter.recordDomainRead("failed");
      return new Response(INTERNAL_BODY, { status: 500, headers: ENVELOPE_JSON_HEADERS });
    }
    if (isInvalidCursor(error)) {
      deps.counter.recordDomainRead("denied");
      return new Response(BAD_REQUEST_BODY, { status: 400, headers: ENVELOPE_JSON_HEADERS });
    }
    deps.counter.recordDomainRead("failed");
    return new Response(INTERNAL_BODY, { status: 500, headers: ENVELOPE_JSON_HEADERS });
  }
};

const isInvalidCursor = (error: unknown): boolean =>
  typeof error === "object" && error !== null
  && (error as { code?: unknown }).code === "invalid_cursor";
