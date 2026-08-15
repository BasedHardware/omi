/**
 * Platform-generation Screen / Rewind transport — the client half of the
 * draft-v1 `/v1/screen` HTTP seam and the consumed native-bridge verbs.
 *
 * Pixels never appear here. Timeline, search, retention, and retired refs
 * travel over HTTP; frame images and capture control stay on the local shell
 * socket. Auth stays with the host (ADR-008 §3): this module takes a relative
 * path and an injected client, never a token or base URL.
 *
 * The draft-v1 wire writes retention with PUT. The ratified `HttpClient` /
 * `BridgeHttpMethod` seam does not include PUT. Callers pass the host client
 * through `asPlatformScreenHttpClient`, which types PUT locally. Native shells
 * that still reject PUT will fail that write until the HTTP seam grows the
 * method; `screen.retentionSet` remains the on-device sweep.
 */

import type { HttpClient, HttpResponse, WriteFailure } from "@omi-core/contracts";
import { classifyStatus } from "@omi-core/kernel";

export const PLATFORM_SCREEN_FRAMES_PATH = "/v1/screen/frames";
export const PLATFORM_SCREEN_TIMELINE_PATH = "/v1/screen/timeline";
export const PLATFORM_SCREEN_DAYS_PATH = "/v1/screen/days";
export const PLATFORM_SCREEN_SEARCH_PATH = "/v1/screen/search";
export const PLATFORM_SCREEN_RETENTION_PATH = "/v1/screen/retention";
export const PLATFORM_SCREEN_RETIRED_PATH = "/v1/screen/retired";

export const SCREEN_SEARCH_DEBOUNCE_MS = 300;
export const SCREEN_SEARCH_GROUP_WINDOW_MS = 30_000;
export const SCREEN_RETENTION_DAYS = [0, 3, 7, 14, 30] as const;
export const SCREEN_RETENTION_DEFAULT_DAYS = 7;

export type ScreenRetentionDays = (typeof SCREEN_RETENTION_DAYS)[number];

export type PlatformScreenHttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * Consumed HTTP surface for this domain. Wider than the ratified `HttpClient`
 * only by PUT, which draft-v1 retention requires.
 */
export interface PlatformScreenHttpClient {
  request(method: PlatformScreenHttpMethod, path: string, body?: unknown): Promise<HttpResponse>;
}

export function asPlatformScreenHttpClient(http: HttpClient): PlatformScreenHttpClient {
  return {
    request(method, path, body) {
      return http.request(method as "GET" | "POST" | "PATCH" | "DELETE", path, body);
    },
  };
}

export type ScreenFrameRefChunk = {
  readonly kind: "chunk";
  readonly path: string;
  readonly offset: number;
};

export type ScreenFrameRefOpaque = {
  readonly kind: "opaque";
  readonly ref: string;
};

export type ScreenFrameRef = ScreenFrameRefChunk | ScreenFrameRefOpaque;

export type ScreenOcrBlock = {
  readonly id: string;
  readonly text: string;
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
  readonly confidence: number;
};

export type ScreenOcrAttachment = {
  readonly full_text: string;
  readonly blocks: readonly ScreenOcrBlock[];
};

export type ScreenTimelineFrame = {
  readonly id: string;
  readonly capture_session_id: string;
  readonly captured_at: string;
  readonly app_bundle_id: string;
  readonly app_name: string;
  readonly window_title: string;
  readonly device_name: string;
  readonly client_device_id: string;
  readonly frame_ref: ScreenFrameRef;
  readonly dhash: string;
};

export type ScreenTimelinePage = {
  readonly day: string;
  readonly frames: readonly ScreenTimelineFrame[];
};

export type ScreenDaySpanSummary = {
  readonly days: readonly string[];
  readonly oldest_captured_at: string | null;
  readonly newest_captured_at: string | null;
  readonly frame_count: number;
};

export type ScreenTextSearchHit = {
  readonly frame_id: string;
  readonly captured_at: string;
  readonly app_bundle_id: string;
  readonly app_name: string;
  readonly window_title: string;
  readonly snippet: string;
  readonly matched_block_ids: readonly string[];
  readonly rank: number;
};

export type ScreenSemanticSearchStatus =
  | { readonly status: "not_configured" }
  | { readonly status: "ready"; readonly hits: readonly ScreenTextSearchHit[] };

export type ScreenTextSearchResponse = {
  readonly query: string;
  readonly hits: readonly ScreenTextSearchHit[];
  readonly semantic: ScreenSemanticSearchStatus;
};

export type ScreenRetentionSetting = {
  readonly days: ScreenRetentionDays;
};

export type ScreenRetiredFrameRef = {
  readonly frame_id: string;
  readonly frame_ref: ScreenFrameRef;
  readonly retired_at: string;
};

export type ScreenRetiredFrameRefsPage = {
  readonly retired: readonly ScreenRetiredFrameRef[];
};

export type PlatformScreenReadOutcome<T> =
  | { readonly kind: "page"; readonly value: T }
  | { readonly kind: "auth-invalid"; readonly status: number }
  | { readonly kind: "unavailable"; readonly status: number }
  | { readonly kind: "unreadable" };

export type PlatformScreenWriteOutcome =
  | { readonly kind: "saved"; readonly setting: ScreenRetentionSetting }
  | { readonly kind: "auth-invalid"; readonly status: number }
  | { readonly kind: "unavailable"; readonly status: number }
  | { readonly kind: "unreadable" }
  | { readonly kind: "failure"; readonly failure: WriteFailure };

export type PlatformScreenCaptureEngineState =
  | "idle"
  | "starting"
  | "recording"
  | "paused"
  | "error";

export type PlatformScreenPermissionState = "granted" | "denied" | "undetermined";

export type PlatformScreenStatus = {
  readonly state: PlatformScreenCaptureEngineState;
  readonly reason: string | null;
  readonly permission: PlatformScreenPermissionState;
  readonly framesStored: number;
  readonly bytesOnDisk: number | null;
  readonly lastCaptureAt: string | null;
};

export type PlatformScreenFrameImage = {
  readonly pngBase64: string;
  readonly width: number;
  readonly height: number;
};

export type PlatformScreenExclusions = {
  readonly bundleIds: readonly string[];
  readonly retiredFrameRefs?: readonly string[];
};

export type PlatformScreenRetentionSweep = {
  readonly days: ScreenRetentionDays;
  readonly retiredFrameRefs: readonly string[];
};

export type PlatformScreenIndexRebuild = {
  readonly frames: number;
  readonly chunks: number;
};

export interface PlatformScreenBridge {
  readonly available: true;
  snapshot(): PlatformScreenStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  start(): Promise<{ sessionId: string; state: PlatformScreenCaptureEngineState }>;
  stop(): Promise<{ state: PlatformScreenCaptureEngineState }>;
  frameImage(input: { frameRef: ScreenFrameRef; maxLongEdge?: number }): Promise<PlatformScreenFrameImage>;
  exclusionsList(): Promise<{ bundleIds: readonly string[] }>;
  exclusionsSet(bundleIds: readonly string[]): Promise<PlatformScreenExclusions>;
  retentionSet(days: ScreenRetentionDays): Promise<PlatformScreenRetentionSweep>;
  rebuildIndex(): Promise<PlatformScreenIndexRebuild>;
  requestPermission(): Promise<{ permission: PlatformScreenPermissionState }>;
  openSettings(): Promise<{ opened: boolean }>;
}

export type PlatformScreenBridgeAccess =
  | PlatformScreenBridge
  | { readonly available: false };

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isCalendarDay(value: unknown): value is string {
  return typeof value === "string" && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value);
}

function ownData(value: unknown, key: string): unknown {
  if (!isRecord(value)) return undefined;
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor !== undefined && "value" in descriptor ? descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

function readOutcomeFromStatus(status: number, transportFailureReason?: string): PlatformScreenReadOutcome<never> {
  if (transportFailureReason === "not-authenticated" || status === 401 || status === 403) {
    return { kind: "auth-invalid", status };
  }
  return { kind: "unavailable", status };
}

function parseFrameRef(raw: unknown): ScreenFrameRef | null {
  if (!isRecord(raw)) return null;
  if (raw["kind"] === "chunk") {
    if (typeof raw["path"] !== "string" || raw["path"].length === 0 || !isNonNegativeInteger(raw["offset"])) {
      return null;
    }
    return { kind: "chunk", path: raw["path"], offset: raw["offset"] };
  }
  if (raw["kind"] === "opaque") {
    if (typeof raw["ref"] !== "string" || raw["ref"].length === 0) return null;
    return { kind: "opaque", ref: raw["ref"] };
  }
  return null;
}

function parseOcrBlock(raw: unknown): ScreenOcrBlock | null {
  if (!isRecord(raw)) return null;
  if (
    typeof raw["id"] !== "string"
    || raw["id"].length === 0
    || typeof raw["text"] !== "string"
    || !isFiniteNumber(raw["x"])
    || !isFiniteNumber(raw["y"])
    || !isFiniteNumber(raw["w"])
    || !isFiniteNumber(raw["h"])
    || !isFiniteNumber(raw["confidence"])
  ) {
    return null;
  }
  if (raw["x"] < 0 || raw["x"] > 1 || raw["y"] < 0 || raw["y"] > 1) return null;
  if (raw["w"] <= 0 || raw["w"] > 1 || raw["h"] <= 0 || raw["h"] > 1) return null;
  if (raw["confidence"] < 0 || raw["confidence"] > 1) return null;
  return {
    id: raw["id"],
    text: raw["text"],
    x: raw["x"],
    y: raw["y"],
    w: raw["w"],
    h: raw["h"],
    confidence: raw["confidence"],
  };
}

export function parseScreenOcrAttachment(raw: unknown): ScreenOcrAttachment | null {
  if (!isRecord(raw) || typeof raw["full_text"] !== "string" || !Array.isArray(raw["blocks"]) || raw["blocks"].length === 0) {
    return null;
  }
  const blocks: ScreenOcrBlock[] = [];
  for (const block of raw["blocks"]) {
    const parsed = parseOcrBlock(block);
    if (parsed === null) return null;
    blocks.push(parsed);
  }
  return { full_text: raw["full_text"], blocks };
}

export function parseScreenTimelineFrame(raw: unknown): ScreenTimelineFrame | null {
  if (!isRecord(raw)) return null;
  const frameRef = parseFrameRef(raw["frame_ref"]);
  if (
    typeof raw["id"] !== "string"
    || raw["id"].length === 0
    || typeof raw["capture_session_id"] !== "string"
    || typeof raw["captured_at"] !== "string"
    || typeof raw["app_bundle_id"] !== "string"
    || typeof raw["app_name"] !== "string"
    || typeof raw["window_title"] !== "string"
    || typeof raw["device_name"] !== "string"
    || typeof raw["client_device_id"] !== "string"
    || typeof raw["dhash"] !== "string"
    || frameRef === null
  ) {
    return null;
  }
  return {
    id: raw["id"],
    capture_session_id: raw["capture_session_id"],
    captured_at: raw["captured_at"],
    app_bundle_id: raw["app_bundle_id"],
    app_name: raw["app_name"],
    window_title: raw["window_title"],
    device_name: raw["device_name"],
    client_device_id: raw["client_device_id"],
    frame_ref: frameRef,
    dhash: raw["dhash"],
  };
}

export function parseScreenTimelinePage(raw: unknown): ScreenTimelinePage | null {
  if (!isRecord(raw) || !isCalendarDay(raw["day"]) || !Array.isArray(raw["frames"])) return null;
  const frames: ScreenTimelineFrame[] = [];
  for (const frame of raw["frames"]) {
    const parsed = parseScreenTimelineFrame(frame);
    if (parsed === null) return null;
    frames.push(parsed);
  }
  return { day: raw["day"], frames };
}

export function parseScreenDaySpanSummary(raw: unknown): ScreenDaySpanSummary | null {
  if (
    !isRecord(raw)
    || !Array.isArray(raw["days"])
    || !isNonNegativeInteger(raw["frame_count"])
    || (raw["oldest_captured_at"] !== null && typeof raw["oldest_captured_at"] !== "string")
    || (raw["newest_captured_at"] !== null && typeof raw["newest_captured_at"] !== "string")
  ) {
    return null;
  }
  const days: string[] = [];
  for (const day of raw["days"]) {
    if (!isCalendarDay(day)) return null;
    days.push(day);
  }
  return {
    days,
    oldest_captured_at: raw["oldest_captured_at"],
    newest_captured_at: raw["newest_captured_at"],
    frame_count: raw["frame_count"],
  };
}

export function parseScreenTextSearchHit(raw: unknown): ScreenTextSearchHit | null {
  if (
    !isRecord(raw)
    || typeof raw["frame_id"] !== "string"
    || raw["frame_id"].length === 0
    || typeof raw["captured_at"] !== "string"
    || typeof raw["app_bundle_id"] !== "string"
    || typeof raw["app_name"] !== "string"
    || typeof raw["window_title"] !== "string"
    || typeof raw["snippet"] !== "string"
    || !Array.isArray(raw["matched_block_ids"])
    || !isFiniteNumber(raw["rank"])
  ) {
    return null;
  }
  const matched: string[] = [];
  for (const id of raw["matched_block_ids"]) {
    if (typeof id !== "string") return null;
    matched.push(id);
  }
  return {
    frame_id: raw["frame_id"],
    captured_at: raw["captured_at"],
    app_bundle_id: raw["app_bundle_id"],
    app_name: raw["app_name"],
    window_title: raw["window_title"],
    snippet: raw["snippet"],
    matched_block_ids: matched,
    rank: raw["rank"],
  };
}

function parseSemantic(raw: unknown): ScreenSemanticSearchStatus | null {
  if (!isRecord(raw) || typeof raw["status"] !== "string") return null;
  if (raw["status"] === "not_configured") return { status: "not_configured" };
  if (raw["status"] !== "ready" || !Array.isArray(raw["hits"])) return null;
  const hits: ScreenTextSearchHit[] = [];
  for (const hit of raw["hits"]) {
    const parsed = parseScreenTextSearchHit(hit);
    if (parsed === null) return null;
    hits.push(parsed);
  }
  return { status: "ready", hits };
}

export function parseScreenTextSearchResponse(raw: unknown): ScreenTextSearchResponse | null {
  if (!isRecord(raw) || typeof raw["query"] !== "string" || !Array.isArray(raw["hits"])) return null;
  const semantic = parseSemantic(raw["semantic"]);
  if (semantic === null) return null;
  const hits: ScreenTextSearchHit[] = [];
  for (const hit of raw["hits"]) {
    const parsed = parseScreenTextSearchHit(hit);
    if (parsed === null) return null;
    hits.push(parsed);
  }
  return { query: raw["query"], hits, semantic };
}

/**
 * Invalid, negative, or unparseable windows fail SAFE to unlimited (0) and
 * never to a deleting window. Mirror of INV-SCREEN-003.
 */
export function coerceScreenRetentionDays(value: unknown): ScreenRetentionDays {
  if (value === 3 || value === 7 || value === 14 || value === 30 || value === 0) return value;
  return 0;
}

export function parseScreenRetentionSetting(raw: unknown): ScreenRetentionSetting | null {
  if (!isRecord(raw) || !("days" in raw)) return null;
  return { days: coerceScreenRetentionDays(raw["days"]) };
}

export function parseScreenRetiredFrameRef(raw: unknown): ScreenRetiredFrameRef | null {
  if (!isRecord(raw) || typeof raw["frame_id"] !== "string" || typeof raw["retired_at"] !== "string") {
    return null;
  }
  const frameRef = parseFrameRef(raw["frame_ref"]);
  if (frameRef === null) return null;
  return { frame_id: raw["frame_id"], frame_ref: frameRef, retired_at: raw["retired_at"] };
}

export function parseScreenRetiredFrameRefsPage(raw: unknown): ScreenRetiredFrameRefsPage | null {
  if (!isRecord(raw) || !Array.isArray(raw["retired"])) return null;
  const retired: ScreenRetiredFrameRef[] = [];
  for (const row of raw["retired"]) {
    const parsed = parseScreenRetiredFrameRef(row);
    if (parsed === null) return null;
    retired.push(parsed);
  }
  return { retired };
}

async function readJson<T>(
  http: PlatformScreenHttpClient,
  method: "GET" | "PUT",
  path: string,
  parse: (raw: unknown) => T | null,
  body?: unknown,
): Promise<PlatformScreenReadOutcome<T>> {
  const response = await http.request(method, path, body);
  if (response.status !== 200) return readOutcomeFromStatus(response.status, response.transportFailureReason);
  const value = parse(response.json);
  return value === null ? { kind: "unreadable" } : { kind: "page", value };
}

export async function fetchScreenTimeline(
  http: PlatformScreenHttpClient,
  day: string,
  options: { readonly limit?: number; readonly offset?: number } = {},
): Promise<PlatformScreenReadOutcome<ScreenTimelinePage>> {
  const query = new URLSearchParams({ day });
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.offset !== undefined) query.set("offset", String(options.offset));
  return readJson(http, "GET", `${PLATFORM_SCREEN_TIMELINE_PATH}?${query.toString()}`, parseScreenTimelinePage);
}

export async function fetchScreenDays(
  http: PlatformScreenHttpClient,
): Promise<PlatformScreenReadOutcome<ScreenDaySpanSummary>> {
  return readJson(http, "GET", PLATFORM_SCREEN_DAYS_PATH, parseScreenDaySpanSummary);
}

export async function fetchScreenSearch(
  http: PlatformScreenHttpClient,
  query: string,
  options: { readonly limit?: number } = {},
): Promise<PlatformScreenReadOutcome<ScreenTextSearchResponse>> {
  const params = new URLSearchParams({ q: query });
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  return readJson(http, "GET", `${PLATFORM_SCREEN_SEARCH_PATH}?${params.toString()}`, parseScreenTextSearchResponse);
}

export async function fetchScreenRetention(
  http: PlatformScreenHttpClient,
): Promise<PlatformScreenReadOutcome<ScreenRetentionSetting>> {
  return readJson(http, "GET", PLATFORM_SCREEN_RETENTION_PATH, parseScreenRetentionSetting);
}

export async function putScreenRetention(
  http: PlatformScreenHttpClient,
  days: ScreenRetentionDays,
): Promise<PlatformScreenWriteOutcome> {
  const response = await http.request("PUT", PLATFORM_SCREEN_RETENTION_PATH, { days });
  if (response.status !== 200) {
    if (response.transportFailureReason === "not-authenticated" || response.status === 401 || response.status === 403) {
      return { kind: "auth-invalid", status: response.status };
    }
    return { kind: "failure", failure: classifyStatus(response, "screen retention") };
  }
  const setting = parseScreenRetentionSetting(response.json);
  return setting === null ? { kind: "unreadable" } : { kind: "saved", setting };
}

export async function fetchScreenRetired(
  http: PlatformScreenHttpClient,
): Promise<PlatformScreenReadOutcome<ScreenRetiredFrameRefsPage>> {
  return readJson(http, "GET", PLATFORM_SCREEN_RETIRED_PATH, parseScreenRetiredFrameRefsPage);
}

const ENGINE_STATES: readonly PlatformScreenCaptureEngineState[] = [
  "idle", "starting", "recording", "paused", "error",
];
const PERMISSIONS: readonly PlatformScreenPermissionState[] = ["granted", "denied", "undetermined"];

export const UNAVAILABLE_SCREEN_STATUS: PlatformScreenStatus = Object.freeze({
  state: "idle",
  reason: null,
  permission: "undetermined",
  framesStored: 0,
  bytesOnDisk: null,
  lastCaptureAt: null,
});

export function freezeScreenStatus(value: unknown): PlatformScreenStatus | null {
  if (!isRecord(value)) return null;
  const state = ownData(value, "state");
  const permission = ownData(value, "permission");
  const framesStored = ownData(value, "framesStored");
  if (
    !ENGINE_STATES.includes(state as PlatformScreenCaptureEngineState)
    || !PERMISSIONS.includes(permission as PlatformScreenPermissionState)
    || !isNonNegativeInteger(framesStored)
  ) {
    return null;
  }
  const reason = ownData(value, "reason");
  const bytesOnDisk = ownData(value, "bytesOnDisk");
  const lastCaptureAt = ownData(value, "lastCaptureAt");
  if (reason !== undefined && reason !== null && typeof reason !== "string") return null;
  if (bytesOnDisk !== undefined && bytesOnDisk !== null && !(typeof bytesOnDisk === "number" && Number.isFinite(bytesOnDisk) && bytesOnDisk >= 0)) {
    return null;
  }
  if (lastCaptureAt !== undefined && lastCaptureAt !== null && typeof lastCaptureAt !== "string") return null;
  return Object.freeze({
    state: state as PlatformScreenCaptureEngineState,
    reason: typeof reason === "string" ? reason : null,
    permission: permission as PlatformScreenPermissionState,
    framesStored,
    bytesOnDisk: typeof bytesOnDisk === "number" ? bytesOnDisk : null,
    lastCaptureAt: typeof lastCaptureAt === "string" ? lastCaptureAt : null,
  });
}

export function createUnavailableScreenBridge(): PlatformScreenBridgeAccess {
  return { available: false };
}
