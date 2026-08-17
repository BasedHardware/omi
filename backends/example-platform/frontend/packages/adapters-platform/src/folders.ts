/**
 * Platform-generation folders adapter — the client half of the ratified
 * folders read seam, plus create/patch/delete on the four verbs already
 * served. Dangling conversation.folder_id after deletion is legal. There is
 * no maximum-folder cap.
 *
 * `complete` is the server's `completeness.status`, never derived.
 */

import type {
  FolderOp,
  FolderPatch,
  HttpClient,
  HttpResponse,
  IdSnapshot,
  PlatformFolderCoverageReason,
  PlatformFolderCoverageState,
  PlatformFolderCoverageStatus,
  PlatformFolderItem,
} from "@omi-core/contracts";
import { classifyStatus } from "@omi-core/kernel";
import type { PendingOp } from "@omi-core/sync";
import {
  MAX_FOLDERS_PAGE_JSON_CODE_UNITS,
  isTrustedFolderPageData,
  parseFolderPageJson,
  type FolderRead,
} from "@omi-core/ratified-contracts/projections/folders";

export const PLATFORM_FOLDERS_READ_PATH = "/v1/folders";
export const PLATFORM_FOLDERS_MAX_LIMIT = 100;
export const PLATFORM_FOLDERS_MAX_PAGES = 200;
export const PLATFORM_FOLDERS_MAX_WALK_ITEMS = 20_000;

export type FolderSendResult =
  | { ok: true; serverRevision?: string; serverAssignedId?: string }
  | { ok: false; failure: import("@omi-core/contracts").WriteFailure };

export async function sendFolderOp(http: HttpClient, op: FolderOp): Promise<FolderSendResult> {
  switch (op.op) {
    case "create": {
      const res = await http.request("POST", "/v1/folders", {
        name: op.name,
        ...(op.description !== undefined ? { description: op.description } : {}),
        ...(op.color !== undefined ? { color: op.color } : {}),
        ...(op.icon !== undefined ? { icon: op.icon } : {}),
      });
      if (res.status === 200 || res.status === 201) {
        const body = res.json as { id?: string };
        return body.id !== undefined ? { ok: true, serverAssignedId: body.id } : { ok: true };
      }
      return { ok: false, failure: classifyStatus(res, `create folder ${op.id}`) };
    }
    case "patch": {
      const res = await http.request("PATCH", `/v1/folders/${encodeURIComponent(op.id)}`, wirePatch(op.patch));
      if (res.status === 200) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `patch folder ${op.id}`) };
    }
    case "delete": {
      const path =
        op.moveToFolderId !== undefined
          ? `/v1/folders/${encodeURIComponent(op.id)}?move_to_folder_id=${encodeURIComponent(op.moveToFolderId)}`
          : `/v1/folders/${encodeURIComponent(op.id)}`;
      const res = await http.request("DELETE", path);
      if (res.status === 200 || res.status === 204) return { ok: true };
      if (res.status === 404) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `delete folder ${op.id}`) };
    }
  }
}

function wirePatch(p: FolderPatch): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (p.name !== undefined) body["name"] = p.name;
  if (p.description !== undefined) body["description"] = p.description;
  if (p.color !== undefined) body["color"] = p.color;
  if (p.icon !== undefined) body["icon"] = p.icon;
  if (p.order !== undefined) body["order"] = p.order;
  return body;
}

export type PlatformFoldersParseBoundary =
  | "canonical-json-text"
  | "trusted-parsed-json";

export type PlatformFoldersPageOutcome =
  | {
      readonly kind: "page";
      readonly page: FolderRead.Page;
      readonly boundary: PlatformFoldersParseBoundary;
    }
  | { readonly kind: "http-error"; readonly status: number }
  | { readonly kind: "unreadable"; readonly boundary: PlatformFoldersParseBoundary };

export interface PlatformFoldersPageRequest {
  readonly limit?: number;
  readonly cursor?: string | null;
  readonly path?: string;
}

export async function fetchPlatformFolderPage(
  http: HttpClient,
  request: PlatformFoldersPageRequest = {},
): Promise<PlatformFoldersPageOutcome> {
  const limit = clampLimit(request.limit);
  const path = request.path ?? PLATFORM_FOLDERS_READ_PATH;
  const query = request.cursor
    ? `?limit=${limit}&cursor=${encodeURIComponent(request.cursor)}`
    : `?limit=${limit}`;
  const res = await http.request("GET", `${path}${query}`);
  if (res.status !== 200) return { kind: "http-error", status: res.status };
  return parsePlatformFolderPageResponse(res);
}

export function parsePlatformFolderPageResponse(res: HttpResponse): PlatformFoldersPageOutcome {
  if (typeof res.text === "string") {
    const page = parseFolderPageJson(res.text);
    return page === null
      ? { kind: "unreadable", boundary: "canonical-json-text" }
      : { kind: "page", page, boundary: "canonical-json-text" };
  }
  if (!isTrustedFolderPageData(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  if (!withinContractSizeCeiling(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  return { kind: "page", page: res.json, boundary: "trusted-parsed-json" };
}

function withinContractSizeCeiling(value: unknown): boolean {
  try {
    return JSON.stringify(value).length <= MAX_FOLDERS_PAGE_JSON_CODE_UNITS;
  } catch {
    return false;
  }
}

function clampLimit(requested: number | undefined): number {
  if (requested === undefined || !Number.isSafeInteger(requested) || requested < 1) {
    return PLATFORM_FOLDERS_MAX_LIMIT;
  }
  return Math.min(requested, PLATFORM_FOLDERS_MAX_LIMIT);
}

export function platformFolderItemsFromPage(page: FolderRead.Page): readonly PlatformFolderItem[] {
  return page.items.map((item): PlatformFolderItem => ({
    id: item.id,
    name: item.name,
    description: item.description,
    color: item.color,
    icon: item.icon,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    order: item.order,
    isDefault: item.isDefault,
    isSystem: item.isSystem,
    revision: item.revision,
  }));
}

export function platformFolderCoverageFromPage(page: FolderRead.Page): PlatformFolderCoverageState {
  const status: PlatformFolderCoverageStatus = page.completeness.status;
  const reasons: readonly PlatformFolderCoverageReason[] = [...page.completeness.reasons];
  return {
    kind: "known",
    status,
    reasons,
    complete: page.completeness.status === "complete",
    queryGap: page.absence !== null,
    hasMore: page.window.hasMore,
  };
}

export interface PlatformFolderWalk {
  readonly items: readonly PlatformFolderItem[];
  readonly coverage: PlatformFolderCoverageState;
  readonly pages: number;
  readonly wholeSet: boolean;
}

export interface PlatformFolderWalkRequest {
  readonly limit?: number;
  readonly path?: string;
  readonly maxPages?: number;
  readonly maxItems?: number;
}

export async function walkPlatformFolderPages(
  http: HttpClient,
  request: PlatformFolderWalkRequest = {},
): Promise<PlatformFolderWalk | null> {
  const maxPages = request.maxPages ?? PLATFORM_FOLDERS_MAX_PAGES;
  const maxItems = request.maxItems ?? PLATFORM_FOLDERS_MAX_WALK_ITEMS;
  const items: PlatformFolderItem[] = [];
  const seenIds = new Set<string>();
  const seenCursors = new Set<string>();
  let cursor: string | null = null;
  let pages = 0;
  let everyPageComplete = true;
  let lastCoverage: PlatformFolderCoverageState = { kind: "unknown" };

  while (pages < maxPages) {
    const pageRequest: PlatformFoldersPageRequest = {
      ...(request.limit !== undefined ? { limit: request.limit } : {}),
      ...(request.path !== undefined ? { path: request.path } : {}),
      cursor,
    };
    const outcome = await fetchPlatformFolderPage(http, pageRequest);
    if (outcome.kind !== "page") return null;
    pages += 1;

    const pageItems = platformFolderItemsFromPage(outcome.page);
    for (const item of pageItems) {
      if (seenIds.has(item.id)) return null;
      seenIds.add(item.id);
    }
    if (items.length + pageItems.length > maxItems) return null;
    items.push(...pageItems);
    lastCoverage = platformFolderCoverageFromPage(outcome.page);
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

export async function fetchPlatformFolderIdSnapshot(
  http: HttpClient,
  request: PlatformFolderWalkRequest = {},
): Promise<IdSnapshot | null> {
  const walk = await walkPlatformFolderPages(http, request);
  if (walk === null) return null;
  const ids = walk.items.map((item) => item.id);
  return {
    setVersion: platformFolderSetVersion(ids, walk.coverage),
    complete: walk.wholeSet,
    ids,
  };
}

function platformFolderSetVersion(
  ids: readonly string[],
  coverage: PlatformFolderCoverageState,
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
  return `pfolder1-${(h >>> 0).toString(16)}`;
}

export function foldersTransport(
  http: HttpClient,
  onServerAssignedId: (localId: string, serverId: string) => void,
  resolveWireId: (localId: string) => string = (id) => id,
): { send(op: PendingOp): Promise<FolderSendResult> } {
  return {
    async send(op: PendingOp): Promise<FolderSendResult> {
      const domainOp = JSON.parse(op.payload) as FolderOp;
      if (domainOp.op !== "create") {
        (domainOp as { id: string }).id = resolveWireId(domainOp.id);
      }
      const result = await sendFolderOp(http, domainOp);
      if (result.ok && result.serverAssignedId !== undefined) {
        onServerAssignedId(domainOp.id, result.serverAssignedId);
      }
      return result;
    },
  };
}
