export const REWIND_MOMENTS_READ_CONTRACT_VERSION = "1.0.0" as const;
export const REWIND_MOMENTS_FRONTIER = "frontier-v1:rewind-moments-declared";

const FRAME_ID = /^[a-z]+:[A-Za-z0-9._:-]{1,200}$/;
const SOURCE = new Set(["captured", "shipping"] as const);

export type RewindMomentRecord = {
  frameId: string;
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
  source: "captured" | "shipping";
  ocrPreview: string;
};

export type RewindMomentPage = {
  contractVersion: typeof REWIND_MOMENTS_READ_CONTRACT_VERSION;
  items: RewindMomentRecord[];
  window: {
    status: "complete" | "more";
    complete: boolean;
    hasMore: boolean;
    nextCursor: string | null;
  };
};

type StoredMoment = {
  frame_id: string;
  captured_at_ms: number;
  app_name: string;
  window_title: string;
  source: string;
  ocr_preview: string;
};

export function parseRewindMomentUpsert(value: unknown): RewindMomentRecord | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const item = value as Record<string, unknown>;
  if (
    typeof item.frameId !== "string" ||
    !FRAME_ID.test(item.frameId) ||
    !Number.isSafeInteger(item.capturedAtMs) ||
    (item.capturedAtMs as number) < 0 ||
    (item.capturedAtMs as number) > 8_640_000_000_000_000 ||
    typeof item.appName !== "string" ||
    item.appName.length === 0 ||
    item.appName.length > 256 ||
    typeof item.windowTitle !== "string" ||
    item.windowTitle.length > 1024 ||
    typeof item.source !== "string" ||
    !SOURCE.has(item.source as "captured" | "shipping") ||
    typeof item.ocrPreview !== "string" ||
    item.ocrPreview.length > 240
  ) {
    return null;
  }
  return {
    frameId: item.frameId,
    capturedAtMs: item.capturedAtMs as number,
    appName: item.appName,
    windowTitle: item.windowTitle,
    source: item.source as "captured" | "shipping",
    ocrPreview: item.ocrPreview,
  };
}

export async function upsertRewindMoment(
  db: D1Database,
  accountId: string,
  moment: RewindMomentRecord,
  now: number
): Promise<RewindMomentRecord | "conflict"> {
  await db
    .prepare(
      `INSERT INTO rewind_moments (
        account_id, frame_id, captured_at_ms, app_name, window_title, source, ocr_preview, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(account_id, frame_id) DO UPDATE SET
        captured_at_ms = excluded.captured_at_ms,
        app_name = excluded.app_name,
        window_title = excluded.window_title,
        source = excluded.source,
        ocr_preview = excluded.ocr_preview,
        updated_at = excluded.updated_at
      WHERE rewind_moments.source = excluded.source`
    )
    .bind(
      accountId,
      moment.frameId,
      moment.capturedAtMs,
      moment.appName,
      moment.windowTitle,
      moment.source,
      moment.ocrPreview,
      now,
      now
    )
    .run();
  const row = await db
    .prepare(
      "SELECT frame_id, captured_at_ms, app_name, window_title, source, ocr_preview FROM rewind_moments WHERE account_id = ? AND frame_id = ?"
    )
    .bind(accountId, moment.frameId)
    .first<StoredMoment>();
  if (row === null) throw new Error("rewind moment insert failed");
  const stored = project(row);
  if (
    stored.capturedAtMs !== moment.capturedAtMs ||
    stored.appName !== moment.appName ||
    stored.windowTitle !== moment.windowTitle ||
    stored.source !== moment.source ||
    stored.ocrPreview !== moment.ocrPreview
  ) {
    return "conflict";
  }
  return stored;
}

export async function readRewindMoments(
  db: D1Database,
  accountId: string,
  limit: number,
  cursor: string | undefined
): Promise<RewindMomentPage | "invalid_cursor"> {
  let beforeMs = 8_640_000_000_000_000;
  let beforeId = "\u007f";
  if (cursor !== undefined) {
    if (!/^[A-Za-z0-9+/=]{8,4096}$/.test(cursor)) return "invalid_cursor";
    let parsed: unknown;
    try {
      parsed = JSON.parse(atob(cursor));
    } catch {
      return "invalid_cursor";
    }
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      Array.isArray(parsed) ||
      !Number.isSafeInteger((parsed as {capturedAtMs?: unknown}).capturedAtMs) ||
      typeof (parsed as {frameId?: unknown}).frameId !== "string"
    ) {
      return "invalid_cursor";
    }
    beforeMs = (parsed as {capturedAtMs: number}).capturedAtMs;
    beforeId = (parsed as {frameId: string}).frameId;
  }
  const result = await db
    .prepare(
      `SELECT frame_id, captured_at_ms, app_name, window_title, source, ocr_preview
       FROM rewind_moments
       WHERE account_id = ?
         AND (captured_at_ms < ? OR (captured_at_ms = ? AND frame_id < ?))
       ORDER BY captured_at_ms DESC, frame_id DESC
       LIMIT ?`
    )
    .bind(accountId, beforeMs, beforeMs, beforeId, limit + 1)
    .all<StoredMoment>();
  const rows = result.results;
  const hasMore = rows.length > limit;
  const pageRows = rows.slice(0, limit).map(project);
  const last = pageRows[pageRows.length - 1];
  const nextCursor =
    hasMore && last !== undefined
      ? btoa(JSON.stringify({capturedAtMs: last.capturedAtMs, frameId: last.frameId}))
      : null;
  return {
    contractVersion: REWIND_MOMENTS_READ_CONTRACT_VERSION,
    items: pageRows,
    window: {
      status: hasMore ? "more" : "complete",
      complete: !hasMore,
      hasMore,
      nextCursor,
    },
  };
}

function project(row: StoredMoment): RewindMomentRecord {
  return {
    frameId: row.frame_id,
    capturedAtMs: row.captured_at_ms,
    appName: row.app_name,
    windowTitle: row.window_title,
    source: row.source as "captured" | "shipping",
    ocrPreview: row.ocr_preview,
  };
}
