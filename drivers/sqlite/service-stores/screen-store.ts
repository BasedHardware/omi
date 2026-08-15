// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import type { Database } from "bun:sqlite";

import type {
  ScreenDaySpanSummary,
  ScreenFrameRecord,
  ScreenFrameRef,
  ScreenIngestOutcome,
  ScreenOcrAttachment,
  ScreenRetiredFrameRef,
  ScreenRetentionSetting,
  ScreenRetentionSweepReport,
  ScreenStore,
  ScreenTextSearchPage,
  ScreenTimelinePage,
} from "../../../apps/service/stores/screen-store";
import {
  SCREEN_DEFAULT_RETENTION_DAYS,
  SCREEN_INGEST_MAX_FRAMES,
  SCREEN_SNIPPET_ELLIPSIS,
  SCREEN_SNIPPET_MARK_END,
  SCREEN_SNIPPET_MARK_START,
  SCREEN_UNLIMITED_RETENTION_DAYS,
  assertCaptureSessionId,
  assertScreenFrameIngestItem,
  fts5MatchQuery,
  isScreenCalendarDay,
  matchedScreenBlockIds,
  parseScreenRetentionDays,
  requireAccountTimezone,
  sameScreenFrame,
  screenCalendarDay,
  screenSearchCorpus,
  screenSearchTokens,
  screenSnippetFor,
} from "../../../apps/service/stores/screen-store";
import { configureServiceStoreConnection } from "./connection";

interface FrameRow {
  readonly rowid: number;
  readonly id: string;
  readonly capture_session_id: string;
  readonly captured_at: string;
  readonly app_bundle_id: string;
  readonly app_name: string;
  readonly window_title: string;
  readonly device_name: string;
  readonly client_device_id: string;
  readonly frame_ref_json: string;
  readonly dhash: string;
  readonly ocr_json: string;
}

interface RetiredRow {
  readonly frame_id: string;
  readonly frame_ref_json: string;
  readonly retired_at: string;
}

const DAY_MS = 86_400_000;

const FRAME_FIELDS = `
  rowid, id, capture_session_id, captured_at, app_bundle_id, app_name,
  window_title, device_name, client_device_id, frame_ref_json, dhash, ocr_json
`;

const toRecord = (row: FrameRow): ScreenFrameRecord => Object.freeze({
  id: row.id,
  captureSessionId: row.capture_session_id,
  capturedAt: row.captured_at,
  appBundleId: row.app_bundle_id,
  appName: row.app_name,
  windowTitle: row.window_title,
  deviceName: row.device_name,
  clientDeviceId: row.client_device_id,
  frameRef: JSON.parse(row.frame_ref_json) as ScreenFrameRef,
  dhash: row.dhash,
  ocr: JSON.parse(row.ocr_json) as ScreenOcrAttachment,
});

const toTimeline = (record: ScreenFrameRecord) => Object.freeze({
  id: record.id,
  capture_session_id: record.captureSessionId,
  captured_at: record.capturedAt,
  app_bundle_id: record.appBundleId,
  app_name: record.appName,
  window_title: record.windowTitle,
  device_name: record.deviceName,
  client_device_id: record.clientDeviceId,
  frame_ref: record.frameRef,
  dhash: record.dhash,
});

const clampPage = (value: number | undefined, fallback: number, max: number): number => {
  if (value === undefined) return fallback;
  if (!Number.isSafeInteger(value) || value < 0) return fallback;
  return Math.min(value, max);
};

/** SQLite persistence for frame metadata, OCR, FTS5 search, and retention. */
export class SqliteScreenStore implements ScreenStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_screen_frames (
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        id TEXT NOT NULL,
        capture_session_id TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        app_bundle_id TEXT NOT NULL,
        app_name TEXT NOT NULL,
        window_title TEXT NOT NULL,
        device_name TEXT NOT NULL,
        client_device_id TEXT NOT NULL,
        frame_ref_json TEXT NOT NULL,
        dhash TEXT NOT NULL,
        ocr_json TEXT NOT NULL,
        ocr_search_text TEXT NOT NULL,
        UNIQUE (account_id, id)
      );
      CREATE INDEX IF NOT EXISTS service_screen_frames_by_captured
        ON service_screen_frames (account_id, captured_at, id);
      CREATE TABLE IF NOT EXISTS service_screen_retention (
        account_id TEXT PRIMARY KEY,
        days INTEGER NOT NULL CHECK (days IN (0, 3, 7, 14, 30))
      );
      CREATE TABLE IF NOT EXISTS service_screen_retired_refs (
        account_id TEXT NOT NULL,
        frame_id TEXT NOT NULL,
        frame_ref_json TEXT NOT NULL,
        retired_at TEXT NOT NULL,
        PRIMARY KEY (account_id, frame_id)
      );
      CREATE INDEX IF NOT EXISTS service_screen_retired_by_account
        ON service_screen_retired_refs (account_id, retired_at, frame_id);
      CREATE VIRTUAL TABLE IF NOT EXISTS service_screen_ocr_fts USING fts5(
        ocr_search_text,
        content='service_screen_frames',
        content_rowid='rowid',
        tokenize='unicode61 remove_diacritics 2'
      );
    `);
  }

  ingest(input: Parameters<ScreenStore["ingest"]>[0]): ScreenIngestOutcome {
    const captureSessionId = assertCaptureSessionId(input.captureSessionId);
    if (!Array.isArray(input.frames) || input.frames.length === 0
      || input.frames.length > SCREEN_INGEST_MAX_FRAMES) {
      throw new TypeError("invalid screen ingest frames");
    }
    const parsed = input.frames.map((frame) =>
      assertScreenFrameIngestItem(frame, captureSessionId));
    const ids = new Set(parsed.map((frame) => frame.id));
    if (ids.size !== parsed.length) throw new TypeError("invalid screen ingest duplicate id");

    const write = this.db.transaction((): ScreenIngestOutcome => {
      const accepted: { readonly id: string; readonly inserted: boolean }[] = [];
      let insertedCount = 0;
      let duplicateCount = 0;
      for (const record of parsed) {
        const existing = this.readFrame(input.accountId, record.id);
        if (existing !== null) {
          if (!sameScreenFrame(existing, record)) {
            throw new TypeError("screen frame id conflict");
          }
          duplicateCount += 1;
          accepted.push(Object.freeze({ id: record.id, inserted: false }));
          continue;
        }
        const searchText = screenSearchCorpus(record.ocr);
        const inserted = this.db.query(`
          INSERT INTO service_screen_frames (
            account_id, id, capture_session_id, captured_at, app_bundle_id,
            app_name, window_title, device_name, client_device_id,
            frame_ref_json, dhash, ocr_json, ocr_search_text
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
          input.accountId,
          record.id,
          record.captureSessionId,
          record.capturedAt,
          record.appBundleId,
          record.appName,
          record.windowTitle,
          record.deviceName,
          record.clientDeviceId,
          JSON.stringify(record.frameRef),
          record.dhash,
          JSON.stringify(record.ocr),
          searchText,
        );
        this.db.query(`
          INSERT INTO service_screen_ocr_fts (rowid, ocr_search_text)
          VALUES (?, ?)
        `).run(Number(inserted.lastInsertRowid), searchText);
        insertedCount += 1;
        accepted.push(Object.freeze({ id: record.id, inserted: true }));
      }
      return Object.freeze({
        captureSessionId,
        accepted: insertedCount,
        duplicate: duplicateCount,
        frames: Object.freeze(accepted),
      });
    });
    return write.immediate();
  }

  listTimeline(
    accountId: string,
    day: string,
    timeZone: string,
    options?: { readonly limit?: number; readonly offset?: number },
  ): ScreenTimelinePage {
    if (!isScreenCalendarDay(day)) throw new TypeError("invalid screen timeline day");
    requireAccountTimezone(timeZone);
    const limit = clampPage(options?.limit, 100, 500);
    const offset = clampPage(options?.offset, 0, Number.MAX_SAFE_INTEGER);
    const rows = this.db.query(`
      SELECT ${FRAME_FIELDS}
      FROM service_screen_frames
      WHERE account_id = ?
      ORDER BY captured_at ASC, id ASC
    `).all(accountId) as FrameRow[];
    const frames = rows
      .map(toRecord)
      .filter((record) => screenCalendarDay(record.capturedAt, timeZone) === day)
      .slice(offset, offset + limit)
      .map(toTimeline);
    return Object.freeze({ day, frames: Object.freeze(frames) });
  }

  daySpan(accountId: string, timeZone: string): ScreenDaySpanSummary {
    requireAccountTimezone(timeZone);
    const rows = this.db.query(`
      SELECT ${FRAME_FIELDS}
      FROM service_screen_frames
      WHERE account_id = ?
      ORDER BY captured_at ASC, id ASC
    `).all(accountId) as FrameRow[];
    const records = rows.map(toRecord);
    const days = [...new Set(records.map((record) => screenCalendarDay(record.capturedAt, timeZone)))]
      .sort();
    return Object.freeze({
      days: Object.freeze(days),
      oldest_captured_at: records[0]?.capturedAt ?? null,
      newest_captured_at: records[records.length - 1]?.capturedAt ?? null,
      frame_count: records.length,
    });
  }

  searchText(
    accountId: string,
    query: string,
    options?: { readonly limit?: number },
  ): ScreenTextSearchPage {
    const tokens = screenSearchTokens(query);
    const limit = clampPage(options?.limit, 20, 100);
    const match = fts5MatchQuery(tokens);
    if (match === null) {
      return Object.freeze({ query, hits: Object.freeze([]) });
    }
    const rows = this.db.query(`
      SELECT
        frames.rowid AS rowid,
        frames.id AS id,
        frames.capture_session_id AS capture_session_id,
        frames.captured_at AS captured_at,
        frames.app_bundle_id AS app_bundle_id,
        frames.app_name AS app_name,
        frames.window_title AS window_title,
        frames.device_name AS device_name,
        frames.client_device_id AS client_device_id,
        frames.frame_ref_json AS frame_ref_json,
        frames.dhash AS dhash,
        frames.ocr_json AS ocr_json,
        bm25(service_screen_ocr_fts) AS rank,
        snippet(
          service_screen_ocr_fts, 0,
          '${SCREEN_SNIPPET_MARK_START}',
          '${SCREEN_SNIPPET_MARK_END}',
          '${SCREEN_SNIPPET_ELLIPSIS}',
          10
        ) AS fts_snippet
      FROM service_screen_ocr_fts
      JOIN service_screen_frames AS frames
        ON frames.rowid = service_screen_ocr_fts.rowid
      WHERE service_screen_ocr_fts MATCH ?
        AND frames.account_id = ?
      ORDER BY rank ASC, frames.captured_at DESC, frames.id ASC
      LIMIT ?
    `).all(match, accountId, limit) as Array<FrameRow & {
      readonly rank: number;
      readonly fts_snippet: string;
    }>;
    const hits = rows.map((row) => {
      const record = toRecord(row);
      const bm25 = typeof row.rank === "number" && Number.isFinite(row.rank) ? row.rank : 0;
      const ftsSnippet = typeof row.fts_snippet === "string" ? row.fts_snippet : "";
      const snippet = ftsSnippet.includes(SCREEN_SNIPPET_MARK_START)
        ? ftsSnippet
        : screenSnippetFor(record.ocr.full_text, tokens);
      return Object.freeze({
        frame_id: record.id,
        captured_at: record.capturedAt,
        app_bundle_id: record.appBundleId,
        app_name: record.appName,
        window_title: record.windowTitle,
        snippet,
        matched_block_ids: matchedScreenBlockIds(record.ocr.blocks, tokens),
        rank: -bm25,
      });
    });
    return Object.freeze({ query, hits: Object.freeze(hits) });
  }

  readRetention(accountId: string): ScreenRetentionSetting {
    const row = this.db.query(`
      SELECT days FROM service_screen_retention WHERE account_id = ?
    `).get(accountId) as { readonly days: number } | null;
    return Object.freeze({
      days: parseScreenRetentionDays(row?.days ?? SCREEN_DEFAULT_RETENTION_DAYS),
    });
  }

  writeRetention(accountId: string, days: unknown, at: string): ScreenRetentionSetting {
    const parsed = parseScreenRetentionDays(days);
    this.db.query(`
      INSERT INTO service_screen_retention (account_id, days)
      VALUES (?, ?)
      ON CONFLICT (account_id) DO UPDATE SET days = excluded.days
    `).run(accountId, parsed);
    this.sweepRetention(at, accountId);
    return Object.freeze({ days: parsed });
  }

  sweepRetention(nowIso: string, accountId?: string): ScreenRetentionSweepReport {
    const nowMs = Date.parse(nowIso);
    if (!Number.isFinite(nowMs) || new Date(nowMs).toISOString() !== nowIso) {
      throw new TypeError("invalid screen sweep instant");
    }
    const write = this.db.transaction((): ScreenRetentionSweepReport => {
      const accountIds = accountId === undefined
        ? this.listedAccountIds()
        : [accountId];
      let deleted = 0;
      let retiredCount = 0;
      let unlimited = 0;
      for (const id of accountIds) {
        const days = this.readRetention(id).days;
        if (days === SCREEN_UNLIMITED_RETENTION_DAYS) {
          unlimited += 1;
          continue;
        }
        const horizon = nowMs - days * DAY_MS;
        const horizonIso = new Date(horizon).toISOString();
        const expired = this.db.query(`
          SELECT ${FRAME_FIELDS}
          FROM service_screen_frames
          WHERE account_id = ? AND captured_at < ?
        `).all(id, horizonIso) as FrameRow[];
        for (const row of expired) {
          this.retireRow(id, row, nowIso);
          deleted += 1;
          retiredCount += 1;
        }
      }
      return Object.freeze({
        scanned_accounts: accountIds.length,
        deleted_frames: deleted,
        retired_frame_refs: retiredCount,
        unlimited_accounts: unlimited,
      });
    });
    return write.immediate();
  }

  listRetiredFrameRefs(accountId: string): readonly ScreenRetiredFrameRef[] {
    const rows = this.db.query(`
      SELECT frame_id, frame_ref_json, retired_at
      FROM service_screen_retired_refs
      WHERE account_id = ?
      ORDER BY retired_at ASC, frame_id ASC
    `).all(accountId) as RetiredRow[];
    return Object.freeze(rows.map((row) => Object.freeze({
      frame_id: row.frame_id,
      frame_ref: JSON.parse(row.frame_ref_json) as ScreenFrameRef,
      retired_at: row.retired_at,
    })));
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_screen_frames;");
      this.db.exec("INSERT INTO service_screen_ocr_fts(service_screen_ocr_fts) VALUES('rebuild');");
      this.db.exec("DELETE FROM service_screen_retention;");
      this.db.exec("DELETE FROM service_screen_retired_refs;");
      this.db.query("DELETE FROM sqlite_sequence WHERE name = ?")
        .run("service_screen_frames");
    });
    reset.immediate();
  }

  private readFrame(accountId: string, frameId: string): ScreenFrameRecord | null {
    const row = this.db.query(`
      SELECT ${FRAME_FIELDS}
      FROM service_screen_frames
      WHERE account_id = ? AND id = ?
    `).get(accountId, frameId) as FrameRow | null;
    return row === null ? null : toRecord(row);
  }

  private listedAccountIds(): readonly string[] {
    const rows = this.db.query(`
      SELECT account_id AS account_id FROM service_screen_frames
      UNION
      SELECT account_id AS account_id FROM service_screen_retention
    `).all() as Array<{ readonly account_id: string }>;
    return rows.map((row) => row.account_id);
  }

  private retireRow(accountId: string, row: FrameRow, at: string): void {
    this.db.query(`
      INSERT INTO service_screen_retired_refs (account_id, frame_id, frame_ref_json, retired_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT (account_id, frame_id) DO NOTHING
    `).run(accountId, row.id, row.frame_ref_json, at);
    this.db.query(`
      INSERT INTO service_screen_ocr_fts (service_screen_ocr_fts, rowid)
      VALUES ('delete', ?)
    `).run(row.rowid);
    this.db.query(`
      DELETE FROM service_screen_frames WHERE account_id = ? AND id = ?
    `).run(accountId, row.id);
  }
}
