/**
 * Platform-generation conversations adapter — the client half of the ratified
 * conversations read seam, plus the four per-field PATCHes and
 * `DELETE ?cascade=false` that stay v1 writes.
 *
 * Reads speak `@omi-core/ratified-contracts` conversations projection. `complete`
 * is the server's `completeness.status`, never derived. Item ids are the
 * storage ids already served, so a platform walk and a legacy offset read of
 * one origin return the same records.
 *
 * Writes are a rename-and-repoint of the legacy adapter onto this origin:
 * same paths, same bodies. There is no client create.
 */

import type {
  ConversationOp,
  ConversationPatch,
  HttpClient,
  HttpResponse,
  IdSnapshot,
  PlatformConversationCoverageReason,
  PlatformConversationCoverageState,
  PlatformConversationCoverageStatus,
  PlatformConversationItem,
} from "@omi-core/contracts";
import { classifyStatus } from "@omi-core/kernel";
import type { PendingOp } from "@omi-core/sync";
import {
  MAX_CONVERSATIONS_PAGE_JSON_CODE_UNITS,
  isTrustedConversationPageData,
  parseConversationPageJson,
  type ConversationRead,
} from "@omi-core/ratified-contracts/projections/conversations";

export const PLATFORM_CONVERSATIONS_READ_PATH = "/v1/conversations";
export const PLATFORM_CONVERSATIONS_MAX_LIMIT = 100;
export const PLATFORM_CONVERSATIONS_MAX_PAGES = 200;
export const PLATFORM_CONVERSATIONS_MAX_WALK_ITEMS = 20_000;

export type ConversationSendResult =
  | { ok: true; serverRevision?: string; serverAssignedId?: string }
  | { ok: false; failure: import("@omi-core/contracts").WriteFailure };

export async function sendConversationOp(
  http: HttpClient,
  op: ConversationOp,
): Promise<ConversationSendResult> {
  switch (op.op) {
    case "patch": {
      for (const step of wirePatchSteps(op.id, op.patch)) {
        const res = await http.request(step.method, step.path, step.body);
        if (res.status !== 200) {
          return { ok: false, failure: classifyStatus(res, `patch conversation ${op.id} (${step.field})`) };
        }
      }
      return { ok: true };
    }
    case "delete": {
      const res = await http.request(
        "DELETE",
        `/v1/conversations/${encodeURIComponent(op.id)}?cascade=false`,
      );
      if (res.status === 200 || res.status === 204) return { ok: true };
      if (res.status === 404) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `delete conversation ${op.id}`) };
    }
  }
}

function wirePatchSteps(
  id: string,
  p: ConversationPatch,
): Array<{ field: string; method: "PATCH"; path: string; body?: unknown }> {
  const steps: Array<{ field: string; method: "PATCH"; path: string; body?: unknown }> = [];
  const encoded = encodeURIComponent(id);
  if (p.title !== undefined) {
    steps.push({
      field: "title",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/title?title=${encodeURIComponent(p.title)}`,
    });
  }
  if (p.starred !== undefined) {
    steps.push({
      field: "starred",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/starred?starred=${p.starred ? "true" : "false"}`,
    });
  }
  if (p.visibility !== undefined) {
    steps.push({
      field: "visibility",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/visibility?value=${encodeURIComponent(p.visibility)}`,
    });
  }
  if (p.folderId !== undefined) {
    steps.push({
      field: "folderId",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/folder`,
      body: { folder_id: p.folderId },
    });
  }
  return steps;
}

export type PlatformConversationsParseBoundary =
  | "canonical-json-text"
  | "trusted-parsed-json";

export type PlatformConversationsPageOutcome =
  | {
      readonly kind: "page";
      readonly page: ConversationRead.Page;
      readonly boundary: PlatformConversationsParseBoundary;
    }
  | { readonly kind: "http-error"; readonly status: number }
  | { readonly kind: "unreadable"; readonly boundary: PlatformConversationsParseBoundary };

export interface PlatformConversationsPageRequest {
  readonly limit?: number;
  readonly cursor?: string | null;
  readonly path?: string;
}

export async function fetchPlatformConversationPage(
  http: HttpClient,
  request: PlatformConversationsPageRequest = {},
): Promise<PlatformConversationsPageOutcome> {
  const limit = clampLimit(request.limit);
  const path = request.path ?? PLATFORM_CONVERSATIONS_READ_PATH;
  const query = request.cursor
    ? `?limit=${limit}&cursor=${encodeURIComponent(request.cursor)}`
    : `?limit=${limit}`;
  const res = await http.request("GET", `${path}${query}`);
  if (res.status !== 200) return { kind: "http-error", status: res.status };
  return parsePlatformConversationPageResponse(res);
}

export function parsePlatformConversationPageResponse(
  res: HttpResponse,
): PlatformConversationsPageOutcome {
  if (typeof res.text === "string") {
    const page = parseConversationPageJson(res.text);
    return page === null
      ? { kind: "unreadable", boundary: "canonical-json-text" }
      : { kind: "page", page, boundary: "canonical-json-text" };
  }
  if (!isTrustedConversationPageData(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  if (!withinContractSizeCeiling(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  return { kind: "page", page: res.json, boundary: "trusted-parsed-json" };
}

function withinContractSizeCeiling(value: unknown): boolean {
  try {
    return JSON.stringify(value).length <= MAX_CONVERSATIONS_PAGE_JSON_CODE_UNITS;
  } catch {
    return false;
  }
}

function clampLimit(requested: number | undefined): number {
  if (requested === undefined || !Number.isSafeInteger(requested) || requested < 1) {
    return PLATFORM_CONVERSATIONS_MAX_LIMIT;
  }
  return Math.min(requested, PLATFORM_CONVERSATIONS_MAX_LIMIT);
}

export function platformConversationItemsFromPage(
  page: ConversationRead.Page,
): readonly PlatformConversationItem[] {
  return page.items.map((item): PlatformConversationItem => ({
    id: item.id,
    title: item.title,
    overview: item.overview,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    startedAt: item.startedAt,
    finishedAt: item.finishedAt,
    source: item.source,
    status: item.status,
    discarded: item.discarded,
    starred: item.starred,
    visibility: item.visibility,
    isLocked: item.isLocked,
    folderId: item.folderId,
    revision: item.revision,
  }));
}

export function platformConversationCoverageFromPage(
  page: ConversationRead.Page,
): PlatformConversationCoverageState {
  const status: PlatformConversationCoverageStatus = page.completeness.status;
  const reasons: readonly PlatformConversationCoverageReason[] = [...page.completeness.reasons];
  return {
    kind: "known",
    status,
    reasons,
    complete: page.completeness.status === "complete",
    queryGap: page.absence !== null,
    hasMore: page.window.hasMore,
  };
}

export interface PlatformConversationWalk {
  readonly items: readonly PlatformConversationItem[];
  readonly coverage: PlatformConversationCoverageState;
  readonly pages: number;
  readonly wholeSet: boolean;
}

export interface PlatformConversationWalkRequest {
  readonly limit?: number;
  readonly path?: string;
  readonly maxPages?: number;
  readonly maxItems?: number;
}

export async function walkPlatformConversationPages(
  http: HttpClient,
  request: PlatformConversationWalkRequest = {},
): Promise<PlatformConversationWalk | null> {
  const maxPages = request.maxPages ?? PLATFORM_CONVERSATIONS_MAX_PAGES;
  const maxItems = request.maxItems ?? PLATFORM_CONVERSATIONS_MAX_WALK_ITEMS;
  const items: PlatformConversationItem[] = [];
  const seenIds = new Set<string>();
  const seenCursors = new Set<string>();
  let cursor: string | null = null;
  let pages = 0;
  let everyPageComplete = true;
  let lastCoverage: PlatformConversationCoverageState = { kind: "unknown" };

  while (pages < maxPages) {
    const pageRequest: PlatformConversationsPageRequest = {
      ...(request.limit !== undefined ? { limit: request.limit } : {}),
      ...(request.path !== undefined ? { path: request.path } : {}),
      cursor,
    };
    const outcome = await fetchPlatformConversationPage(http, pageRequest);
    if (outcome.kind !== "page") return null;
    pages += 1;

    const pageItems = platformConversationItemsFromPage(outcome.page);
    for (const item of pageItems) {
      if (seenIds.has(item.id)) return null;
      seenIds.add(item.id);
    }
    if (items.length + pageItems.length > maxItems) return null;
    items.push(...pageItems);
    lastCoverage = platformConversationCoverageFromPage(outcome.page);
    if (outcome.page.completeness.status !== "complete") everyPageComplete = false;

    const window = outcome.page.window;
    if (!window.hasMore) {
      return {
        items,
        coverage: lastCoverage,
        pages,
        wholeSet: everyPageComplete && window.status === "complete",
      };
    }
    if (seenCursors.has(window.nextCursor)) return null;
    seenCursors.add(window.nextCursor);
    cursor = window.nextCursor;
  }
  return { items, coverage: lastCoverage, pages, wholeSet: false };
}

export async function fetchPlatformConversationIdSnapshot(
  http: HttpClient,
  request: PlatformConversationWalkRequest = {},
): Promise<IdSnapshot | null> {
  const walk = await walkPlatformConversationPages(http, request);
  if (walk === null) return null;
  const ids = walk.items.map((item) => item.id);
  return {
    setVersion: platformConversationSetVersion(ids, walk.coverage),
    complete: walk.wholeSet,
    ids,
  };
}

function platformConversationSetVersion(
  ids: readonly string[],
  coverage: PlatformConversationCoverageState,
): string {
  let h = 0x811c9dc5;
  const feed = (value: string): void => {
    for (let index = 0; index < value.length; index++) {
      h ^= value.charCodeAt(index);
      h = Math.imul(h, 0x01000193);
    }
    h ^= 0x2c;
    h = Math.imul(h, 0x01000193);
  };
  for (const id of [...ids].sort()) feed(id);
  feed(coverage.kind === "known" ? coverage.status : "unknown");
  return `pconv1-${(h >>> 0).toString(16)}`;
}

export function conversationsTransport(
  http: HttpClient,
  onServerAssignedId: (localId: string, serverId: string) => void,
): { send(op: PendingOp): Promise<ConversationSendResult> } {
  return {
    async send(op: PendingOp): Promise<ConversationSendResult> {
      const domainOp = JSON.parse(op.payload) as ConversationOp;
      const result = await sendConversationOp(http, domainOp);
      if (result.ok && result.serverAssignedId !== undefined) {
        onServerAssignedId(domainOp.id, result.serverAssignedId);
      }
      return result;
    },
  };
}

