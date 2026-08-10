// domain-pending(DIV-DOMCORE-012)

import type { Database } from "bun:sqlite";

import type {
  AppendListenSegmentOutcome,
  ListenSessionRecord,
  ListenSessionStatus,
  ListenStore,
  ListenTranscriptSegment,
  OpenListenSessionInput,
  OpenListenSessionOutcome,
} from "../../../apps/service/stores/listen-store";
import { configureServiceStoreConnection } from "./connection";

interface SessionRow {
  readonly id: string;
  readonly conversation_id: string;
  readonly client_conversation_id: string | null;
  readonly started_at: string;
  readonly updated_at: string;
  readonly ended_at: string | null;
  readonly status: ListenSessionStatus;
  readonly source: string | null;
  readonly codec: string;
  readonly sample_rate: number;
  readonly channels: number;
}

interface SegmentRow {
  readonly id: string;
  readonly text: string;
  readonly is_user: number;
  readonly start_seconds: number;
  readonly end_seconds: number;
}

const toSession = (row: SessionRow): ListenSessionRecord => Object.freeze({
  id: row.id,
  conversationId: row.conversation_id,
  clientConversationId: row.client_conversation_id,
  startedAt: row.started_at,
  updatedAt: row.updated_at,
  endedAt: row.ended_at,
  status: row.status,
  source: row.source,
  codec: row.codec,
  sampleRate: row.sample_rate,
  channels: row.channels,
});

const toSegment = (row: SegmentRow): ListenTranscriptSegment => Object.freeze({
  id: row.id,
  text: row.text,
  is_user: row.is_user === 1,
  start: row.start_seconds,
  end: row.end_seconds,
});

const sameSegment = (left: ListenTranscriptSegment, right: ListenTranscriptSegment): boolean =>
  left.id === right.id
  && left.text === right.text
  && left.is_user === right.is_user
  && left.start === right.start
  && left.end === right.end;

const SESSION_FIELDS = `
  id, conversation_id, client_conversation_id, started_at, updated_at,
  ended_at, status, source, codec, sample_rate, channels
`;

const SEGMENT_FIELDS = "id, text, is_user, start_seconds, end_seconds";

/** SQLite persistence for recording sessions, transcript ids, and delivery state. */
export class SqliteListenStore implements ListenStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_listen_sessions (
        account_id TEXT NOT NULL,
        id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        client_conversation_id TEXT,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        ended_at TEXT,
        status TEXT NOT NULL CHECK (
          status IN ('active', 'interrupted', 'completed', 'entitlement_exhausted')
        ),
        source TEXT,
        codec TEXT NOT NULL,
        sample_rate INTEGER NOT NULL CHECK (sample_rate > 0),
        channels INTEGER NOT NULL CHECK (channels > 0),
        PRIMARY KEY (account_id, id),
        UNIQUE (account_id, conversation_id),
        UNIQUE (account_id, client_conversation_id)
      );
      CREATE TABLE IF NOT EXISTS service_listen_transcript_segments (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        id TEXT NOT NULL,
        text TEXT NOT NULL,
        is_user INTEGER NOT NULL CHECK (is_user IN (0, 1)),
        start_seconds REAL NOT NULL CHECK (start_seconds >= 0),
        end_seconds REAL NOT NULL CHECK (end_seconds >= start_seconds),
        delivered INTEGER NOT NULL DEFAULT 0 CHECK (delivered IN (0, 1)),
        created_at TEXT NOT NULL,
        UNIQUE (account_id, session_id, id),
        FOREIGN KEY (account_id, session_id)
          REFERENCES service_listen_sessions (account_id, id)
          ON DELETE CASCADE
      );
      CREATE INDEX IF NOT EXISTS service_listen_segments_by_session
        ON service_listen_transcript_segments (account_id, session_id, sequence);
      CREATE INDEX IF NOT EXISTS service_listen_pending_segments
        ON service_listen_transcript_segments (account_id, session_id, delivered, sequence);
    `);
  }

  openOrResume(input: OpenListenSessionInput): OpenListenSessionOutcome {
    const write = this.db.transaction((): OpenListenSessionOutcome => {
      const existing = this.readSession(input.accountId, input.id);
      if (existing !== null) {
        if (existing.conversationId !== input.conversationId
          || existing.clientConversationId !== input.clientConversationId) {
          throw new TypeError("listen session binding conflict");
        }
        this.db.query(`
          UPDATE service_listen_sessions
          SET status = 'active', ended_at = NULL, updated_at = ?
          WHERE account_id = ? AND id = ?
        `).run(input.at, input.accountId, input.id);
        return Object.freeze({
          session: this.readSession(input.accountId, input.id)!,
          resumed: true,
          pendingSegments: this.listSegments(input.accountId, input.id),
        });
      }
      this.db.query(`
        INSERT INTO service_listen_sessions (
          account_id, id, conversation_id, client_conversation_id,
          started_at, updated_at, ended_at, status, source, codec, sample_rate, channels
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'active', ?, ?, ?, ?)
      `).run(
        input.accountId,
        input.id,
        input.conversationId,
        input.clientConversationId,
        input.at,
        input.at,
        input.source,
        input.codec,
        input.sampleRate,
        input.channels,
      );
      return Object.freeze({
        session: this.readSession(input.accountId, input.id)!,
        resumed: false,
        pendingSegments: Object.freeze([]),
      });
    });
    return write.immediate();
  }

  appendSegment(
    accountId: string,
    sessionId: string,
    segment: ListenTranscriptSegment,
    at: string,
  ): AppendListenSegmentOutcome {
    const write = this.db.transaction((): AppendListenSegmentOutcome => {
      const inserted = this.db.query(`
        INSERT OR IGNORE INTO service_listen_transcript_segments (
          account_id, session_id, id, text, is_user,
          start_seconds, end_seconds, delivered, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
      `).run(
        accountId,
        sessionId,
        segment.id,
        segment.text,
        segment.is_user ? 1 : 0,
        segment.start,
        segment.end,
        at,
      );
      const stored = this.readSegment(accountId, sessionId, segment.id);
      if (stored === null) throw new TypeError("listen session not found");
      if (!sameSegment(stored, segment)) throw new TypeError("listen segment id conflict");
      if (inserted.changes > 0) {
        this.db.query(`
          UPDATE service_listen_sessions SET updated_at = ?
          WHERE account_id = ? AND id = ?
        `).run(at, accountId, sessionId);
      }
      return Object.freeze({ segment: stored, inserted: inserted.changes > 0 });
    });
    return write.immediate();
  }

  markDelivered(accountId: string, sessionId: string, segmentIds: readonly string[]): void {
    if (segmentIds.length === 0) return;
    const placeholders = segmentIds.map(() => "?").join(", ");
    this.db.query(`
      UPDATE service_listen_transcript_segments SET delivered = 1
      WHERE account_id = ? AND session_id = ? AND id IN (${placeholders})
    `).run(accountId, sessionId, ...segmentIds);
  }

  pendingSegments(accountId: string, sessionId: string): readonly ListenTranscriptSegment[] {
    const rows = this.db.query(`
      SELECT ${SEGMENT_FIELDS}
      FROM service_listen_transcript_segments
      WHERE account_id = ? AND session_id = ? AND delivered = 0
      ORDER BY sequence ASC
    `).all(accountId, sessionId) as SegmentRow[];
    return Object.freeze(rows.map(toSegment));
  }

  closeSession(
    accountId: string,
    sessionId: string,
    status: Exclude<ListenSessionStatus, "active">,
    at: string,
  ): ListenSessionRecord | null {
    this.db.query(`
      UPDATE service_listen_sessions
      SET status = ?, ended_at = ?, updated_at = ?
      WHERE account_id = ? AND id = ?
    `).run(status, at, at, accountId, sessionId);
    return this.readSession(accountId, sessionId);
  }

  readSession(accountId: string, sessionId: string): ListenSessionRecord | null {
    const row = this.db.query(`
      SELECT ${SESSION_FIELDS}
      FROM service_listen_sessions
      WHERE account_id = ? AND id = ?
    `).get(accountId, sessionId) as SessionRow | null;
    return row === null ? null : toSession(row);
  }

  listSegments(accountId: string, sessionId: string): readonly ListenTranscriptSegment[] {
    const rows = this.db.query(`
      SELECT ${SEGMENT_FIELDS}
      FROM service_listen_transcript_segments
      WHERE account_id = ? AND session_id = ?
      ORDER BY sequence ASC
    `).all(accountId, sessionId) as SegmentRow[];
    return Object.freeze(rows.map(toSegment));
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_listen_transcript_segments;");
      this.db.exec("DELETE FROM service_listen_sessions;");
      this.db.query("DELETE FROM sqlite_sequence WHERE name = ?")
        .run("service_listen_transcript_segments");
    });
    reset.immediate();
  }

  private readSegment(
    accountId: string,
    sessionId: string,
    segmentId: string,
  ): ListenTranscriptSegment | null {
    const row = this.db.query(`
      SELECT ${SEGMENT_FIELDS}
      FROM service_listen_transcript_segments
      WHERE account_id = ? AND session_id = ? AND id = ?
    `).get(accountId, sessionId, segmentId) as SegmentRow | null;
    return row === null ? null : toSegment(row);
  }
}
