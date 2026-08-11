// domain-pending(DIV-DOMTASK-001)
/**
 * DATED, FEATURE-FROZEN LEGACY ACTION-ITEMS COMPATIBILITY FAMILY.
 *
 * Historical authority: `backend/routers/action_items.py @ e0893286`.
 * Settled decision: `FABLE-single-service-generation-compatibility.md` (2026-08-10).
 * Feature freeze: only the five invocations used by the shipped Tasks adapter
 * belong here; every new Tasks capability belongs on `/v1/tasks` or
 * `/v1/tasks/ops`.
 * Deletion trigger: delete this family in the same release series in which
 * David ratifies the Tasks platform generation and its real-account
 * migration/default flip.
 */

import { createHash } from "node:crypto";
import type { Context, Hono } from "hono";

import type { DevPrincipal } from "../auth/dev-token";
import type { TasksRecord, TasksStore } from "../stores/tasks-store";

export const ACTION_ITEMS_COMPAT_PATH = "/v1/action-items";
export const ACTION_ITEMS_COMPAT_IDS_PATH = `${ACTION_ITEMS_COMPAT_PATH}/ids`;

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });
const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const NOT_FOUND_BODY = JSON.stringify({ error: "not_found" });
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });
const MAX_BODY_CODE_UNITS = 65_536;
const MAX_CREATE_ID_ATTEMPTS = 32;
const SAFE_LEGACY_ID = /^[A-Za-z0-9_-]{4,128}$/;
const HISTORICAL_TASK_OWNERS = new Set(["user", "other", "unknown"]);
const PRIVATE_CREATE_DIGEST_KEY = "__omi.legacy.action_items.create_digest.v1";
const FROZEN_STATIC_SIBLINGS = new Set([
  "batch",
  "batch-delete",
  "ids",
  "pending-sync",
  "search",
  "share",
  "shared",
  "sync-batch",
]);
const ACCOUNT_OVERRIDE_HEADERS = Object.freeze([
  "account-id",
  "account_id",
  "x-account-id",
  "x-omi-account-id",
]);

interface LegacyActionItemRow {
  readonly id: string;
  readonly description: string;
  readonly completed: boolean;
  readonly completed_at: string | null;
  readonly due_at: string | null;
  readonly owner: string | null;
  readonly source: string;
  readonly provenance: readonly string[];
  readonly sort_order: number;
  readonly indent_level: number;
  readonly created_at: string;
  readonly updated_at: string;
}

interface CreateInput {
  readonly description: string;
  readonly dueAt: number | null;
  readonly source: string;
}

interface PatchInput {
  readonly description?: string;
  readonly completed?: boolean;
  readonly dueAt?: number | null;
  readonly owner?: string;
  readonly sortOrder?: number;
  readonly indentLevel?: number;
}

export interface ActionItemsCompatRouteDependencies {
  /** The same resolver every app-facing route uses; null includes lifecycle revocation. */
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  /** The one Tasks authority shared with `/v1/tasks` and `/v1/tasks/ops`. */
  readonly store: TasksStore;
  /** Injected epoch-millisecond clock. A successful create/update samples it once. */
  readonly nowEpochMilliseconds: () => number;
  /** Injected server-id factory. The released create wire carries no client id. */
  readonly createId: () => string;
}

class InvalidStoredActionItemError extends Error {}

const fixedResponse = (body: string, status: number): Response =>
  new Response(body, { status, headers: JSON_HEADERS });

const jsonResponse = (value: unknown, status = 200): Response =>
  new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const principalOf = (
  context: Context,
  resolvePrincipal: (token: string) => DevPrincipal | null,
): DevPrincipal | null => {
  const token = bearerToken(context.req.header("authorization"));
  return token === null ? null : resolvePrincipal(token);
};

const hasAccountOverrideHeader = (context: Context): boolean =>
  ACCOUNT_OVERRIDE_HEADERS.some((name) => context.req.raw.headers.has(name));

const hasJsonContentType = (context: Context): boolean =>
  context.req.header("content-type")?.split(";", 1)[0]?.trim().toLowerCase() === "application/json";

const hasNoQuery = (rawUrl: string): boolean => {
  try {
    return [...new URL(rawUrl).searchParams.keys()].length === 0;
  } catch {
    return false;
  }
};

const parseListQuery = (rawUrl: string): { readonly limit: number; readonly offset: number } | null => {
  let parameters: URLSearchParams;
  try {
    parameters = new URL(rawUrl).searchParams;
  } catch {
    return null;
  }
  const keys = [...parameters.keys()];
  if (keys.some((key) => key !== "limit" && key !== "offset")) return null;
  if (parameters.getAll("limit").length > 1 || parameters.getAll("offset").length > 1) return null;

  const integer = (raw: string | null, fallback: number): number | null => {
    if (raw === null) return fallback;
    if (!/^\d+$/.test(raw)) return null;
    const value = Number(raw);
    return Number.isSafeInteger(value) ? value : null;
  };
  const limit = integer(parameters.get("limit"), 50);
  const offset = integer(parameters.get("offset"), 0);
  if (limit === null || offset === null || limit < 1 || limit > 500 || offset < 0) return null;
  return Object.freeze({ limit, offset });
};

const parseBodyObject = async (context: Context): Promise<Record<string, unknown> | null> => {
  let raw: string;
  try {
    raw = await context.req.text();
  } catch {
    return null;
  }
  if (raw.length === 0 || raw.length > MAX_BODY_CODE_UNITS) return null;
  try {
    const value = JSON.parse(raw) as unknown;
    if (typeof value !== "object" || value === null || Array.isArray(value)
      || Object.getPrototypeOf(value) !== Object.prototype) return null;
    return value as Record<string, unknown>;
  } catch {
    return null;
  }
};

const hasExactAllowedKeys = (
  value: Readonly<Record<string, unknown>>,
  allowed: ReadonlySet<string>,
): boolean => Object.keys(value).every((key) => allowed.has(key))
  && !["__proto__", "constructor", "prototype"].some((key) =>
    Object.prototype.hasOwnProperty.call(value, key));

/** Adapter-emitted ISO 8601 with an explicit UTC offset, losslessly reducible to epoch milliseconds. */
const parseIsoEpochMilliseconds = (value: unknown): number | undefined => {
  if (typeof value !== "string") return undefined;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (match === null) return undefined;
  const yearRaw = match[1];
  const monthRaw = match[2];
  const dayRaw = match[3];
  const hourRaw = match[4];
  const minuteRaw = match[5];
  const secondRaw = match[6];
  const zone = match[8];
  if (yearRaw === undefined || monthRaw === undefined || dayRaw === undefined
    || hourRaw === undefined || minuteRaw === undefined || secondRaw === undefined
    || zone === undefined) return undefined;
  const year = Number(yearRaw);
  const month = Number(monthRaw);
  const day = Number(dayRaw);
  const hour = Number(hourRaw);
  const minute = Number(minuteRaw);
  const second = Number(secondRaw);
  if (year < 1) return undefined;
  const milliseconds = Number((match[7] ?? "0").padEnd(3, "0"));
  // Date.UTC remaps years 0..99 to 1900..1999. Setting the full year explicitly
  // preserves Python's historical aware-datetime range without changing storage.
  const wallDate = new Date(0);
  wallDate.setUTCFullYear(year, month - 1, day);
  wallDate.setUTCHours(hour, minute, second, milliseconds);
  const wall = wallDate.getTime();
  if (wallDate.getUTCFullYear() !== year || wallDate.getUTCMonth() !== month - 1
    || wallDate.getUTCDate() !== day || wallDate.getUTCHours() !== hour
    || wallDate.getUTCMinutes() !== minute || wallDate.getUTCSeconds() !== second
    || wallDate.getUTCMilliseconds() !== milliseconds) return undefined;

  let offsetMinutes = 0;
  if (zone !== "Z") {
    const offset = /^([+-])(\d{2}):(\d{2})$/.exec(zone);
    if (offset === null) return undefined;
    const offsetSign = offset[1];
    const offsetHoursRaw = offset[2];
    const offsetRemainderRaw = offset[3];
    if (offsetSign === undefined || offsetHoursRaw === undefined || offsetRemainderRaw === undefined) {
      return undefined;
    }
    const offsetHours = Number(offsetHoursRaw);
    const offsetRemainder = Number(offsetRemainderRaw);
    if (offsetHours > 23 || offsetRemainder > 59) return undefined;
    offsetMinutes = (offsetHours * 60 + offsetRemainder) * (offsetSign === "+" ? 1 : -1);
  }
  const epoch = wall - offsetMinutes * 60_000;
  if (!Number.isSafeInteger(epoch)) return undefined;
  const normalized = new Date(epoch);
  const normalizedYear = normalized.getUTCFullYear();
  if (normalizedYear < 1 || normalizedYear > 9_999) return undefined;
  const projected = normalized.toISOString();
  return /^\d{4}-/.test(projected) ? epoch : undefined;
};

const parseCreate = (body: Readonly<Record<string, unknown>>): CreateInput | null => {
  if (!hasExactAllowedKeys(body, new Set(["description", "due_at", "source"]))) return null;
  const description = body["description"];
  if (typeof description !== "string" || description.length < 1
    || description.length > 4_096) return null;
  let dueAt: number | null = null;
  const dueAtValue = body["due_at"];
  if (Object.prototype.hasOwnProperty.call(body, "due_at") && dueAtValue !== null) {
    const parsed = parseIsoEpochMilliseconds(dueAtValue);
    if (parsed === undefined) return null;
    dueAt = parsed;
  }
  const source = Object.prototype.hasOwnProperty.call(body, "source") ? body["source"] : "manual";
  if (typeof source !== "string" || source.length < 1 || source.length > 64) return null;
  return Object.freeze({ description, dueAt, source });
};

const parsePatch = (body: Readonly<Record<string, unknown>>): PatchInput | null => {
  const allowed = new Set([
    "description",
    "completed",
    "due_at",
    "owner",
    "sort_order",
    "indent_level",
  ]);
  if (!hasExactAllowedKeys(body, allowed) || Object.keys(body).length === 0) return null;
  const patch: {
    description?: string;
    completed?: boolean;
    dueAt?: number | null;
    owner?: string;
    sortOrder?: number;
    indentLevel?: number;
  } = {};
  if (Object.prototype.hasOwnProperty.call(body, "description")) {
    const description = body["description"];
    if (typeof description !== "string" || description.length < 1
      || description.length > 4_096) return null;
    patch.description = description;
  }
  if (Object.prototype.hasOwnProperty.call(body, "completed")) {
    const completed = body["completed"];
    if (typeof completed !== "boolean") return null;
    patch.completed = completed;
  }
  if (Object.prototype.hasOwnProperty.call(body, "due_at")) {
    const dueAt = body["due_at"];
    if (dueAt === null) patch.dueAt = null;
    else {
      const parsed = parseIsoEpochMilliseconds(dueAt);
      if (parsed === undefined) return null;
      patch.dueAt = parsed;
    }
  }
  if (Object.prototype.hasOwnProperty.call(body, "owner")) {
    const owner = body["owner"];
    if (typeof owner !== "string" || !HISTORICAL_TASK_OWNERS.has(owner)) return null;
    patch.owner = owner;
  }
  if (Object.prototype.hasOwnProperty.call(body, "sort_order")) {
    const sortOrder = body["sort_order"];
    if (typeof sortOrder !== "number" || !Number.isSafeInteger(sortOrder)) return null;
    patch.sortOrder = sortOrder;
  }
  if (Object.prototype.hasOwnProperty.call(body, "indent_level")) {
    const indentLevel = body["indent_level"];
    if (!Number.isSafeInteger(indentLevel) || typeof indentLevel !== "number"
      || indentLevel < 0 || indentLevel > 3) return null;
    patch.indentLevel = indentLevel;
  }
  return Object.freeze(patch);
};

/** Exact historical idempotency framing, exported only for executable compatibility proof. */
export const actionItemsCompatCreateDigest = (accountId: string, description: string): string =>
  createHash("sha256")
    .update(`${accountId.length}:${accountId}:${description.trim().toLowerCase()}`, "utf8")
    .digest("hex");

const injectedNow = (clock: () => number): number => {
  const value = clock();
  if (!Number.isSafeInteger(value) || value < 0) throw new TypeError("invalid compatibility clock");
  return value;
};

const iso = (value: number | null): string | null => value === null ? null : new Date(value).toISOString();

const projectRecord = (record: TasksRecord): LegacyActionItemRow => {
  const bag = record.content;
  const description = bag["description"];
  const completed = bag["completed"];
  const completedAt = bag["completedAt"];
  const dueAt = bag["dueAt"];
  const owner = bag["owner"];
  const source = bag["source"];
  const provenance = bag["provenance"];
  const sortOrder = bag["sortOrder"];
  const indentLevel = bag["indentLevel"];
  const createdAt = bag["createdAt"];
  const updatedAt = bag["updatedAt"];
  if (typeof description !== "string" || typeof completed !== "boolean"
    || (completedAt !== null && !Number.isSafeInteger(completedAt))
    || (dueAt !== null && !Number.isSafeInteger(dueAt))
    || (owner !== null && typeof owner !== "string") || typeof source !== "string"
    || !Array.isArray(provenance) || !provenance.every((entry) => typeof entry === "string")
    || typeof sortOrder !== "number" || !Number.isFinite(sortOrder)
    || !Number.isSafeInteger(indentLevel) || (indentLevel as number) < 0
    || !Number.isSafeInteger(createdAt) || !Number.isSafeInteger(updatedAt)) {
    throw new InvalidStoredActionItemError();
  }
  return Object.freeze({
    id: record.record_id,
    description,
    completed,
    completed_at: iso(completedAt as number | null),
    due_at: iso(dueAt as number | null),
    owner: owner as string | null,
    source,
    provenance: Object.freeze([...provenance] as string[]),
    sort_order: sortOrder,
    indent_level: indentLevel as number,
    created_at: iso(createdAt as number)!,
    updated_at: iso(updatedAt as number)!,
  });
};

const allocateFreshId = (deps: ActionItemsCompatRouteDependencies, accountId: string): string => {
  for (let attempt = 0; attempt < MAX_CREATE_ID_ATTEMPTS; attempt += 1) {
    const id = deps.createId();
    if (typeof id !== "string" || !SAFE_LEGACY_ID.test(id)) {
      throw new TypeError("invalid compatibility id");
    }
    if (deps.store.readRecord(accountId, id) === null) return id;
  }
  throw new TypeError("compatibility id factory did not produce a fresh id");
};

/**
 * LOAD-BEARING SINGLE-PROCESS CRITICAL REGION.
 *
 * The request body is completely parsed before this synchronous helper is
 * entered. From the first retry/live-id observation through `TasksStore.apply`
 * there is deliberately no `await`, so another request cannot interleave this
 * region on one Bun service event loop. This is not a cross-process claim: the
 * compatibility target is one service process with one SQLite authority.
 */
const createOrReuseActionItem = (
  deps: ActionItemsCompatRouteDependencies,
  accountId: string,
  input: CreateInput,
): TasksRecord => {
  const digest = actionItemsCompatCreateDigest(accountId, input.description);
  const retry = deps.store.listRecords(accountId).find((record) =>
    record.content["completed"] === false && record.content[PRIVATE_CREATE_DIGEST_KEY] === digest);
  if (retry !== undefined) return retry;

  const now = injectedNow(deps.nowEpochMilliseconds);
  const id = allocateFreshId(deps, accountId);
  const applied = deps.store.apply(accountId, {
    op: "create",
    record_id: id,
    content: Object.freeze({
      description: input.description,
      completed: false,
      completedAt: null,
      dueAt: input.dueAt,
      owner: "user",
      source: input.source,
      provenance: Object.freeze([]),
      sortOrder: 0,
      indentLevel: 0,
      createdAt: now,
      updatedAt: now,
      [PRIVATE_CREATE_DIGEST_KEY]: digest,
    }),
  });
  if (!applied.applied) throw new TypeError("unconditional compatibility create conflicted");
  const stored = deps.store.readRecord(accountId, id);
  if (stored === null) throw new TypeError("compatibility create was not readable");
  return stored;
};

const guarded = (handler: (context: Context, principal: DevPrincipal) => Response | Promise<Response>, deps: ActionItemsCompatRouteDependencies) =>
  async (context: Context): Promise<Response> => {
    const principal = principalOf(context, deps.resolvePrincipal);
    if (principal === null) return fixedResponse(UNAUTHORIZED_BODY, 401);
    try {
      return await handler(context, principal);
    } catch {
      return fixedResponse(INTERNAL_BODY, 500);
    }
  };

/** Used by the actual-response evidence classifier; status is checked by its caller. */
export const isActionItemsCompatInvocation = (method: string, path: string): boolean => {
  if (method === "GET" && (path === ACTION_ITEMS_COMPAT_PATH || path === ACTION_ITEMS_COMPAT_IDS_PATH)) {
    return true;
  }
  if (method === "POST") return path === ACTION_ITEMS_COMPAT_PATH;
  if (method !== "PATCH" && method !== "DELETE") return false;
  const prefix = `${ACTION_ITEMS_COMPAT_PATH}/`;
  if (!path.startsWith(prefix)) return false;
  const encodedId = path.slice(prefix.length);
  if (encodedId.length === 0 || encodedId.includes("/")) return false;
  let id: string;
  try {
    id = decodeURIComponent(encodedId);
  } catch {
    return false;
  }
  return !FROZEN_STATIC_SIBLINGS.has(id) && SAFE_LEGACY_ID.test(id);
};

export const registerActionItemsCompatRoutes = (
  app: Hono,
  deps: ActionItemsCompatRouteDependencies,
): void => {
  app.get(ACTION_ITEMS_COMPAT_IDS_PATH, guarded((context, principal) => {
    if (hasAccountOverrideHeader(context) || !hasNoQuery(context.req.url)) {
      return fixedResponse(BAD_REQUEST_BODY, 400);
    }
    return jsonResponse({ ids: deps.store.listRecords(principal.uid).map((record) => record.record_id) });
  }, deps));

  app.get(ACTION_ITEMS_COMPAT_PATH, guarded((context, principal) => {
    if (hasAccountOverrideHeader(context)) return fixedResponse(BAD_REQUEST_BODY, 400);
    const page = parseListQuery(context.req.url);
    if (page === null) return fixedResponse(BAD_REQUEST_BODY, 400);
    const fetched = deps.store.listRecords(principal.uid).slice(page.offset, page.offset + page.limit + 1);
    return jsonResponse({
      action_items: fetched.slice(0, page.limit).map(projectRecord),
      has_more: fetched.length > page.limit,
    });
  }, deps));

  app.post(ACTION_ITEMS_COMPAT_PATH, guarded(async (context, principal) => {
    if (hasAccountOverrideHeader(context) || !hasNoQuery(context.req.url) || !hasJsonContentType(context)) {
      return fixedResponse(BAD_REQUEST_BODY, 400);
    }
    const raw = await parseBodyObject(context);
    const input = raw === null ? null : parseCreate(raw);
    if (input === null) return fixedResponse(BAD_REQUEST_BODY, 400);
    return jsonResponse(projectRecord(createOrReuseActionItem(deps, principal.uid, input)));
  }, deps));

  app.patch(`${ACTION_ITEMS_COMPAT_PATH}/:id`, guarded(async (context, principal) => {
    const id = context.req.param("id");
    if (id === undefined) return fixedResponse(NOT_FOUND_BODY, 404);
    if (FROZEN_STATIC_SIBLINGS.has(id)) return fixedResponse(NOT_FOUND_BODY, 404);
    if (hasAccountOverrideHeader(context) || !hasNoQuery(context.req.url) || !hasJsonContentType(context)) {
      return fixedResponse(BAD_REQUEST_BODY, 400);
    }
    if (!SAFE_LEGACY_ID.test(id)) return fixedResponse(BAD_REQUEST_BODY, 400);
    const raw = await parseBodyObject(context);
    const input = raw === null ? null : parsePatch(raw);
    if (input === null) return fixedResponse(BAD_REQUEST_BODY, 400);
    // Load-bearing: TasksStore patch upserts an absent id. Keep this synchronous
    // preflight adjacent to `apply`; there is no await between them in one service.
    if (deps.store.readRecord(principal.uid, id) === null) return fixedResponse(NOT_FOUND_BODY, 404);

    const now = injectedNow(deps.nowEpochMilliseconds);
    const patch: Record<string, unknown> = { updatedAt: now };
    if (input.description !== undefined) patch["description"] = input.description;
    if (input.completed !== undefined) {
      patch["completed"] = input.completed;
      patch["completedAt"] = input.completed ? now : null;
    }
    if (input.dueAt !== undefined) patch["dueAt"] = input.dueAt;
    if (input.owner !== undefined) patch["owner"] = input.owner;
    if (input.sortOrder !== undefined) patch["sortOrder"] = input.sortOrder;
    if (input.indentLevel !== undefined) patch["indentLevel"] = input.indentLevel;
    const applied = deps.store.apply(principal.uid, { op: "patch", record_id: id, patch });
    if (!applied.applied) throw new TypeError("unconditional compatibility patch conflicted");
    const stored = deps.store.readRecord(principal.uid, id);
    if (stored === null) throw new TypeError("compatibility patch was not readable");
    return jsonResponse(projectRecord(stored));
  }, deps));

  app.delete(`${ACTION_ITEMS_COMPAT_PATH}/:id`, guarded((context, principal) => {
    if (hasAccountOverrideHeader(context) || !hasNoQuery(context.req.url)
      || context.req.raw.body !== null) {
      return fixedResponse(BAD_REQUEST_BODY, 400);
    }
    const id = context.req.param("id");
    if (id === undefined) return fixedResponse(NOT_FOUND_BODY, 404);
    if (FROZEN_STATIC_SIBLINGS.has(id)) return fixedResponse(NOT_FOUND_BODY, 404);
    if (!SAFE_LEGACY_ID.test(id)) return fixedResponse(BAD_REQUEST_BODY, 400);
    // Load-bearing: TasksStore delete reports applied for an absent id. Keep
    // this synchronous preflight adjacent to `apply` in the one-service target.
    if (deps.store.readRecord(principal.uid, id) === null) return fixedResponse(NOT_FOUND_BODY, 404);
    const applied = deps.store.apply(principal.uid, { op: "delete", record_id: id });
    if (!applied.applied) throw new TypeError("unconditional compatibility delete conflicted");
    return new Response(null, { status: 204 });
  }, deps));
};
