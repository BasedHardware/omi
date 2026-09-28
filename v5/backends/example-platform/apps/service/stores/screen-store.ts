// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

/**
 * Durable service-side state for the legacy screen-recording vocabulary.
 *
 * Pixels never enter this store. A row is metadata, OCR text, block geometry,
 * a perceptual dhash, and a client-local frame_ref the native lane uses to
 * garbage-collect its own H.265 chunks after retention.
 */

export const SCREEN_RETENTION_DAYS = Object.freeze([0, 3, 7, 14, 30] as const);
export type ScreenRetentionDays = (typeof SCREEN_RETENTION_DAYS)[number];
export const SCREEN_DEFAULT_RETENTION_DAYS: ScreenRetentionDays = 7;
export const SCREEN_UNLIMITED_RETENTION_DAYS: ScreenRetentionDays = 0;
export const SCREEN_INGEST_MAX_FRAMES = 100;
export const SCREEN_SNIPPET_MARK_START = "<<";
export const SCREEN_SNIPPET_MARK_END = ">>";
export const SCREEN_SNIPPET_ELLIPSIS = "…";
const DAY_MS = 86_400_000;
const COORD_SLOP = 1e-4;

export type ScreenFrameRef =
  | { readonly kind: "chunk"; readonly path: string; readonly offset: number }
  | { readonly kind: "opaque"; readonly ref: string };

export interface ScreenOcrBlock {
  readonly id: string;
  readonly text: string;
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
  readonly confidence: number;
}

export interface ScreenOcrAttachment {
  readonly full_text: string;
  readonly blocks: readonly ScreenOcrBlock[];
}

export interface ScreenFrameRecord {
  readonly id: string;
  readonly captureSessionId: string;
  readonly capturedAt: string;
  readonly appBundleId: string;
  readonly appName: string;
  readonly windowTitle: string;
  readonly deviceName: string;
  readonly clientDeviceId: string;
  readonly frameRef: ScreenFrameRef;
  readonly dhash: string;
  readonly ocr: ScreenOcrAttachment;
}

export interface ScreenFrameIngestItem {
  readonly id: string;
  readonly captured_at: string;
  readonly app_bundle_id: string;
  readonly app_name: string;
  readonly window_title: string;
  readonly device_name: string;
  readonly client_device_id: string;
  readonly frame_ref: ScreenFrameRef;
  readonly dhash: string;
  readonly ocr: ScreenOcrAttachment;
}

export interface ScreenIngestInput {
  readonly accountId: string;
  readonly captureSessionId: string;
  readonly frames: readonly ScreenFrameIngestItem[];
}

export interface ScreenIngestAccepted {
  readonly id: string;
  readonly inserted: boolean;
}

export interface ScreenIngestOutcome {
  readonly captureSessionId: string;
  readonly accepted: number;
  readonly duplicate: number;
  readonly frames: readonly ScreenIngestAccepted[];
}

export interface ScreenTimelineFrame {
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
}

export interface ScreenTimelinePage {
  readonly day: string;
  readonly frames: readonly ScreenTimelineFrame[];
}

export interface ScreenDaySpanSummary {
  readonly days: readonly string[];
  readonly oldest_captured_at: string | null;
  readonly newest_captured_at: string | null;
  readonly frame_count: number;
}

export interface ScreenTextSearchHit {
  readonly frame_id: string;
  readonly captured_at: string;
  readonly app_bundle_id: string;
  readonly app_name: string;
  readonly window_title: string;
  readonly snippet: string;
  readonly matched_block_ids: readonly string[];
  readonly rank: number;
}

export interface ScreenTextSearchPage {
  readonly query: string;
  readonly hits: readonly ScreenTextSearchHit[];
}

export interface ScreenRetentionSetting {
  readonly days: ScreenRetentionDays;
}

export interface ScreenRetiredFrameRef {
  readonly frame_id: string;
  readonly frame_ref: ScreenFrameRef;
  readonly retired_at: string;
}

export interface ScreenRetentionSweepReport {
  readonly scanned_accounts: number;
  readonly deleted_frames: number;
  readonly retired_frame_refs: number;
  readonly unlimited_accounts: number;
}

export interface ScreenStore {
  ingest(input: ScreenIngestInput): ScreenIngestOutcome;
  listTimeline(
    accountId: string,
    day: string,
    timeZone: string,
    options?: { readonly limit?: number; readonly offset?: number },
  ): ScreenTimelinePage;
  daySpan(accountId: string, timeZone: string): ScreenDaySpanSummary;
  searchText(
    accountId: string,
    query: string,
    options?: { readonly limit?: number },
  ): ScreenTextSearchPage;
  readRetention(accountId: string): ScreenRetentionSetting;
  writeRetention(accountId: string, days: unknown, at: string): ScreenRetentionSetting;
  sweepRetention(nowIso: string, accountId?: string): ScreenRetentionSweepReport;
  listRetiredFrameRefs(accountId: string): readonly ScreenRetiredFrameRef[];
  reset(): void;
}

const freezeRef = (ref: ScreenFrameRef): ScreenFrameRef =>
  ref.kind === "chunk"
    ? Object.freeze({ kind: "chunk" as const, path: ref.path, offset: ref.offset })
    : Object.freeze({ kind: "opaque" as const, ref: ref.ref });

const freezeBlock = (block: ScreenOcrBlock): ScreenOcrBlock => Object.freeze({ ...block });

const freezeOcr = (ocr: ScreenOcrAttachment): ScreenOcrAttachment =>
  Object.freeze({
    full_text: ocr.full_text,
    blocks: Object.freeze(ocr.blocks.map(freezeBlock)),
  });

const freezeRecord = (record: ScreenFrameRecord): ScreenFrameRecord => Object.freeze({
  ...record,
  frameRef: freezeRef(record.frameRef),
  ocr: freezeOcr(record.ocr),
});

const freezeTimeline = (record: ScreenFrameRecord): ScreenTimelineFrame => Object.freeze({
  id: record.id,
  capture_session_id: record.captureSessionId,
  captured_at: record.capturedAt,
  app_bundle_id: record.appBundleId,
  app_name: record.appName,
  window_title: record.windowTitle,
  device_name: record.deviceName,
  client_device_id: record.clientDeviceId,
  frame_ref: freezeRef(record.frameRef),
  dhash: record.dhash,
});

export const sameFrameRef = (left: ScreenFrameRef, right: ScreenFrameRef): boolean => {
  if (left.kind !== right.kind) return false;
  if (left.kind === "chunk" && right.kind === "chunk") {
    return left.path === right.path && left.offset === right.offset;
  }
  if (left.kind === "opaque" && right.kind === "opaque") return left.ref === right.ref;
  return false;
};

const sameBlocks = (
  left: readonly ScreenOcrBlock[],
  right: readonly ScreenOcrBlock[],
): boolean => left.length === right.length
  && left.every((block, index) => {
    const other = right[index];
    return other !== undefined
      && block.id === other.id
      && block.text === other.text
      && block.x === other.x
      && block.y === other.y
      && block.w === other.w
      && block.h === other.h
      && block.confidence === other.confidence;
  });

export const sameScreenFrame = (left: ScreenFrameRecord, right: ScreenFrameRecord): boolean =>
  left.id === right.id
  && left.captureSessionId === right.captureSessionId
  && left.capturedAt === right.capturedAt
  && left.appBundleId === right.appBundleId
  && left.appName === right.appName
  && left.windowTitle === right.windowTitle
  && left.deviceName === right.deviceName
  && left.clientDeviceId === right.clientDeviceId
  && left.dhash === right.dhash
  && sameFrameRef(left.frameRef, right.frameRef)
  && left.ocr.full_text === right.ocr.full_text
  && sameBlocks(left.ocr.blocks, right.ocr.blocks);

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const requireFiniteString = (value: unknown, label: string): string => {
  if (typeof value !== "string") throw new TypeError(`invalid screen ${label}`);
  return value;
};

const requireNonEmptyString = (value: unknown, label: string): string => {
  const text = requireFiniteString(value, label);
  if (text.length === 0) throw new TypeError(`invalid screen ${label}`);
  return text;
};

const requireIsoInstant = (value: unknown, label: string): string => {
  const text = requireNonEmptyString(value, label);
  const parsed = Date.parse(text);
  if (!Number.isFinite(parsed) || new Date(parsed).toISOString() !== text) {
    throw new TypeError(`invalid screen ${label}`);
  }
  return text;
};

const requireUnitInterval = (value: unknown, label: string, options?: {
  readonly exclusiveMin?: boolean;
}): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError(`invalid screen ${label}`);
  }
  if (options?.exclusiveMin === true ? value <= 0 : value < 0) {
    throw new TypeError(`invalid screen ${label}`);
  }
  if (value > 1) throw new TypeError(`invalid screen ${label}`);
  return value;
};

export const assertScreenFrameRef = (value: unknown): ScreenFrameRef => {
  if (!isPlainObject(value)) throw new TypeError("invalid screen frame_ref");
  const keys = Object.keys(value);
  if (value.kind === "chunk") {
    if (keys.length !== 3 || !keys.includes("kind") || !keys.includes("path") || !keys.includes("offset")) {
      throw new TypeError("invalid screen frame_ref");
    }
    const path = requireNonEmptyString(value.path, "frame_ref.path");
    if (typeof value.offset !== "number" || !Number.isSafeInteger(value.offset) || value.offset < 0) {
      throw new TypeError("invalid screen frame_ref.offset");
    }
    return freezeRef({ kind: "chunk", path, offset: value.offset });
  }
  if (value.kind === "opaque") {
    if (keys.length !== 2 || !keys.includes("kind") || !keys.includes("ref")) {
      throw new TypeError("invalid screen frame_ref");
    }
    return freezeRef({ kind: "opaque", ref: requireNonEmptyString(value.ref, "frame_ref.ref") });
  }
  throw new TypeError("invalid screen frame_ref");
};

export const assertScreenOcrBlock = (value: unknown, fallbackId: string): ScreenOcrBlock => {
  if (!isPlainObject(value)) throw new TypeError("invalid screen ocr block");
  const id = value.id === undefined ? fallbackId : requireNonEmptyString(value.id, "ocr.block.id");
  const text = requireFiniteString(value.text, "ocr.block.text");
  const x = requireUnitInterval(value.x, "ocr.block.x");
  const y = requireUnitInterval(value.y, "ocr.block.y");
  const w = requireUnitInterval(value.w, "ocr.block.w", { exclusiveMin: true });
  const h = requireUnitInterval(value.h, "ocr.block.h", { exclusiveMin: true });
  if (x + w > 1 + COORD_SLOP || y + h > 1 + COORD_SLOP) {
    throw new TypeError("invalid screen ocr block geometry");
  }
  const confidence = requireUnitInterval(value.confidence, "ocr.block.confidence");
  return freezeBlock({ id, text, x, y, w, h, confidence });
};

export const assertScreenOcr = (value: unknown): ScreenOcrAttachment => {
  if (!isPlainObject(value)) throw new TypeError("invalid screen ocr");
  const fullText = requireFiniteString(value.full_text, "ocr.full_text");
  if (!Array.isArray(value.blocks) || value.blocks.length === 0) {
    throw new TypeError("invalid screen ocr.blocks");
  }
  const blocks = value.blocks.map((block, index) => assertScreenOcrBlock(block, String(index)));
  const ids = new Set(blocks.map((block) => block.id));
  if (ids.size !== blocks.length) throw new TypeError("invalid screen ocr.block.id");
  return freezeOcr({ full_text: fullText, blocks: Object.freeze(blocks) });
};

const FORBIDDEN_PIXEL_KEYS = Object.freeze([
  "pixels",
  "image",
  "png",
  "jpeg",
  "jpg",
  "chunk_bytes",
  "chunkBytes",
  "data",
  "base64",
]);

export const assertScreenFrameIngestItem = (
  value: unknown,
  captureSessionId: string,
): ScreenFrameRecord => {
  if (!isPlainObject(value)) throw new TypeError("invalid screen frame");
  for (const key of FORBIDDEN_PIXEL_KEYS) {
    if (key in value) throw new TypeError("screen pixels must not cross the wire");
  }
  const record = freezeRecord({
    id: requireNonEmptyString(value.id, "frame.id"),
    captureSessionId,
    capturedAt: requireIsoInstant(value.captured_at, "captured_at"),
    appBundleId: requireFiniteString(value.app_bundle_id, "app_bundle_id"),
    appName: requireFiniteString(value.app_name, "app_name"),
    windowTitle: requireFiniteString(value.window_title, "window_title"),
    deviceName: requireFiniteString(value.device_name, "device_name"),
    clientDeviceId: requireNonEmptyString(value.client_device_id, "client_device_id"),
    frameRef: assertScreenFrameRef(value.frame_ref),
    dhash: requireNonEmptyString(value.dhash, "dhash"),
    ocr: assertScreenOcr(value.ocr),
  });
  return record;
};

export const assertCaptureSessionId = (value: unknown): string =>
  requireNonEmptyString(value, "capture_session_id");

export const isScreenRetentionDays = (value: unknown): value is ScreenRetentionDays =>
  typeof value === "number"
  && Number.isSafeInteger(value)
  && (SCREEN_RETENTION_DAYS as readonly number[]).includes(value);

/**
 * Retention parse with the legacy fail-safe: 0 is unlimited, and anything that
 * is not an allowed window becomes unlimited rather than a deleting window.
 */
export const parseScreenRetentionDays = (value: unknown): ScreenRetentionDays => {
  if (isScreenRetentionDays(value)) return value;
  if (typeof value === "string" && /^-?[0-9]+$/.test(value)) {
    const parsed = Number(value);
    if (isScreenRetentionDays(parsed)) return parsed;
  }
  return SCREEN_UNLIMITED_RETENTION_DAYS;
};

export const requireAccountTimezone = (value: string): string => {
  if (value.length === 0) throw new TypeError("invalid screen timezone");
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(0);
  } catch {
    throw new TypeError("invalid screen timezone");
  }
  return value;
};

const DAY_FORMATTER_CACHE = new Map<string, Intl.DateTimeFormat>();

const dayFormatter = (timeZone: string): Intl.DateTimeFormat => {
  const existing = DAY_FORMATTER_CACHE.get(timeZone);
  if (existing !== undefined) return existing;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: requireAccountTimezone(timeZone),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  DAY_FORMATTER_CACHE.set(timeZone, formatter);
  return formatter;
};

export const screenCalendarDay = (isoInstant: string, timeZone: string): string =>
  dayFormatter(timeZone).format(new Date(isoInstant));

export const isScreenCalendarDay = (value: string): boolean =>
  /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value);

export const normalizeScreenText = (value: string): string =>
  value.normalize("NFKC").toLowerCase().replace(/\s+/g, " ").trim();

export const screenSearchTokens = (query: string): readonly string[] => {
  const normalized = normalizeScreenText(query);
  if (normalized.length === 0) return Object.freeze([]);
  return Object.freeze(normalized.split(" ").filter((token) => token.length > 0));
};

export const screenSearchCorpus = (ocr: ScreenOcrAttachment): string =>
  normalizeScreenText([ocr.full_text, ...ocr.blocks.map((block) => block.text)].join(" "));

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export const screenSnippetFor = (fullText: string, tokens: readonly string[]): string => {
  if (tokens.length === 0) return "";
  const source = fullText.length > 0 ? fullText : "";
  const haystack = source.normalize("NFKC");
  const lower = haystack.toLowerCase();
  let matchAt = -1;
  let matchLength = 0;
  for (const token of tokens) {
    const at = lower.indexOf(token);
    if (at >= 0 && (matchAt < 0 || at < matchAt)) {
      matchAt = at;
      matchLength = token.length;
    }
  }
  if (matchAt < 0) return `${SCREEN_SNIPPET_ELLIPSIS}${haystack.slice(0, 80)}${SCREEN_SNIPPET_ELLIPSIS}`;
  const window = 40;
  const start = Math.max(0, matchAt - window);
  const end = Math.min(haystack.length, matchAt + matchLength + window);
  const prefix = start > 0 ? SCREEN_SNIPPET_ELLIPSIS : "";
  const suffix = end < haystack.length ? SCREEN_SNIPPET_ELLIPSIS : "";
  const excerpt = haystack.slice(start, end);
  const localAt = matchAt - start;
  const wrapped = `${excerpt.slice(0, localAt)}${SCREEN_SNIPPET_MARK_START}${excerpt.slice(localAt, localAt + matchLength)}${SCREEN_SNIPPET_MARK_END}${excerpt.slice(localAt + matchLength)}`;
  return `${prefix}${wrapped}${suffix}`;
};

export const matchedScreenBlockIds = (
  blocks: readonly ScreenOcrBlock[],
  tokens: readonly string[],
): readonly string[] => {
  if (tokens.length === 0) return Object.freeze([]);
  const matched: string[] = [];
  for (const block of blocks) {
    const text = normalizeScreenText(block.text);
    if (tokens.some((token) => text.includes(token))) matched.push(block.id);
  }
  return Object.freeze(matched);
};

export const rankScreenMatch = (corpus: string, tokens: readonly string[]): number => {
  if (tokens.length === 0) return 0;
  let score = 0;
  for (const token of tokens) {
    if (!corpus.includes(token)) return 0;
    const matches = corpus.match(new RegExp(escapeRegExp(token), "g"));
    score += matches?.length ?? 0;
  }
  if (tokens.length > 1 && corpus.includes(tokens.join(" "))) score += 2;
  return score;
};

export const fts5MatchQuery = (tokens: readonly string[]): string | null => {
  if (tokens.length === 0) return null;
  const quoted: string[] = [];
  for (const token of tokens) {
    const cleaned = token.replace(/"/g, "");
    if (cleaned.length === 0) continue;
    quoted.push(`"${cleaned}"`);
  }
  if (quoted.length === 0) return null;
  return quoted.join(" AND ");
};

const clampPage = (value: number | undefined, fallback: number, max: number): number => {
  if (value === undefined) return fallback;
  if (!Number.isSafeInteger(value) || value < 0) return fallback;
  return Math.min(value, max);
};

const retentionHorizonMs = (days: ScreenRetentionDays, nowMs: number): number | null => {
  if (days === SCREEN_UNLIMITED_RETENTION_DAYS) return null;
  return nowMs - days * DAY_MS;
};

/** Hermetic adapter used by the local service and HTTP tests. */
export const createInMemoryScreenStore = (): ScreenStore => {
  const frames = new Map<string, Map<string, ScreenFrameRecord>>();
  const retention = new Map<string, ScreenRetentionDays>();
  const retired = new Map<string, ScreenRetiredFrameRef[]>();
  const accountFrames = (accountId: string): Map<string, ScreenFrameRecord> => {
    const existing = frames.get(accountId);
    if (existing !== undefined) return existing;
    const created = new Map<string, ScreenFrameRecord>();
    frames.set(accountId, created);
    return created;
  };

  const retire = (
    accountId: string,
    record: ScreenFrameRecord,
    at: string,
  ): void => {
    const rows = retired.get(accountId) ?? [];
    if (!rows.some((row) => row.frame_id === record.id)) {
      rows.push(Object.freeze({
        frame_id: record.id,
        frame_ref: freezeRef(record.frameRef),
        retired_at: at,
      }));
      retired.set(accountId, rows);
    }
    accountFrames(accountId).delete(record.id);
  };

  return Object.freeze({
    ingest(input: ScreenIngestInput): ScreenIngestOutcome {
      const captureSessionId = assertCaptureSessionId(input.captureSessionId);
      if (!Array.isArray(input.frames) || input.frames.length === 0
        || input.frames.length > SCREEN_INGEST_MAX_FRAMES) {
        throw new TypeError("invalid screen ingest frames");
      }
      const parsed = input.frames.map((frame) =>
        assertScreenFrameIngestItem(frame, captureSessionId));
      const ids = new Set(parsed.map((frame) => frame.id));
      if (ids.size !== parsed.length) throw new TypeError("invalid screen ingest duplicate id");
      const owned = accountFrames(input.accountId);
      const accepted: ScreenIngestAccepted[] = [];
      let insertedCount = 0;
      let duplicateCount = 0;
      for (const record of parsed) {
        const existing = owned.get(record.id);
        if (existing !== undefined) {
          if (!sameScreenFrame(existing, record)) {
            throw new TypeError("screen frame id conflict");
          }
          duplicateCount += 1;
          accepted.push(Object.freeze({ id: record.id, inserted: false }));
          continue;
        }
        owned.set(record.id, record);
        insertedCount += 1;
        accepted.push(Object.freeze({ id: record.id, inserted: true }));
      }
      return Object.freeze({
        captureSessionId,
        accepted: insertedCount,
        duplicate: duplicateCount,
        frames: Object.freeze(accepted),
      });
    },

    listTimeline(accountId, day, timeZone, options): ScreenTimelinePage {
      if (!isScreenCalendarDay(day)) throw new TypeError("invalid screen timeline day");
      requireAccountTimezone(timeZone);
      const limit = clampPage(options?.limit, 100, 500);
      const offset = clampPage(options?.offset, 0, Number.MAX_SAFE_INTEGER);
      const owned = [...accountFrames(accountId).values()]
        .filter((record) => screenCalendarDay(record.capturedAt, timeZone) === day)
        .sort((left, right) => left.capturedAt < right.capturedAt
          ? -1
          : left.capturedAt > right.capturedAt
            ? 1
            : left.id.localeCompare(right.id));
      return Object.freeze({
        day,
        frames: Object.freeze(owned.slice(offset, offset + limit).map(freezeTimeline)),
      });
    },

    daySpan(accountId, timeZone): ScreenDaySpanSummary {
      requireAccountTimezone(timeZone);
      const owned = [...accountFrames(accountId).values()]
        .sort((left, right) => left.capturedAt < right.capturedAt
          ? -1
          : left.capturedAt > right.capturedAt
            ? 1
            : left.id.localeCompare(right.id));
      const days = [...new Set(owned.map((record) => screenCalendarDay(record.capturedAt, timeZone)))]
        .sort();
      return Object.freeze({
        days: Object.freeze(days),
        oldest_captured_at: owned[0]?.capturedAt ?? null,
        newest_captured_at: owned[owned.length - 1]?.capturedAt ?? null,
        frame_count: owned.length,
      });
    },

    searchText(accountId, query, options): ScreenTextSearchPage {
      const tokens = screenSearchTokens(query);
      const limit = clampPage(options?.limit, 20, 100);
      if (tokens.length === 0) {
        return Object.freeze({ query, hits: Object.freeze([]) });
      }
      const hits: ScreenTextSearchHit[] = [];
      for (const record of accountFrames(accountId).values()) {
        const corpus = screenSearchCorpus(record.ocr);
        const rank = rankScreenMatch(corpus, tokens);
        if (rank <= 0) continue;
        hits.push(Object.freeze({
          frame_id: record.id,
          captured_at: record.capturedAt,
          app_bundle_id: record.appBundleId,
          app_name: record.appName,
          window_title: record.windowTitle,
          snippet: screenSnippetFor(record.ocr.full_text, tokens),
          matched_block_ids: matchedScreenBlockIds(record.ocr.blocks, tokens),
          rank,
        }));
      }
      hits.sort((left, right) => right.rank - left.rank
        || (right.captured_at < left.captured_at ? -1 : right.captured_at > left.captured_at ? 1 : 0)
        || left.frame_id.localeCompare(right.frame_id));
      return Object.freeze({
        query,
        hits: Object.freeze(hits.slice(0, limit)),
      });
    },

    readRetention(accountId): ScreenRetentionSetting {
      return Object.freeze({
        days: parseScreenRetentionDays(retention.get(accountId) ?? SCREEN_DEFAULT_RETENTION_DAYS),
      });
    },

    writeRetention(accountId, days, at): ScreenRetentionSetting {
      const parsed = parseScreenRetentionDays(days);
      retention.set(accountId, parsed);
      this.sweepRetention(at, accountId);
      return Object.freeze({ days: parsed });
    },

    sweepRetention(nowIso, accountId): ScreenRetentionSweepReport {
      const nowMs = Date.parse(nowIso);
      if (!Number.isFinite(nowMs) || new Date(nowMs).toISOString() !== nowIso) {
        throw new TypeError("invalid screen sweep instant");
      }
      const accountIds = accountId === undefined
        ? [...new Set([...frames.keys(), ...retention.keys()])]
        : [accountId];
      let deleted = 0;
      let retiredCount = 0;
      let unlimited = 0;
      for (const id of accountIds) {
        const days = parseScreenRetentionDays(retention.get(id) ?? SCREEN_DEFAULT_RETENTION_DAYS);
        if (days === SCREEN_UNLIMITED_RETENTION_DAYS) {
          unlimited += 1;
          continue;
        }
        const horizon = retentionHorizonMs(days, nowMs);
        if (horizon === null) continue;
        const owned = accountFrames(id);
        for (const record of [...owned.values()]) {
          const capturedMs = Date.parse(record.capturedAt);
          // Keep a frame exactly at the cap; delete only when strictly older.
          if (capturedMs < horizon) {
            retire(id, record, nowIso);
            deleted += 1;
            retiredCount += 1;
          }
        }
      }
      return Object.freeze({
        scanned_accounts: accountIds.length,
        deleted_frames: deleted,
        retired_frame_refs: retiredCount,
        unlimited_accounts: unlimited,
      });
    },

    listRetiredFrameRefs(accountId): readonly ScreenRetiredFrameRef[] {
      return Object.freeze([...(retired.get(accountId) ?? [])]);
    },

    reset(): void {
      frames.clear();
      retention.clear();
      retired.clear();
    },
  });
};
