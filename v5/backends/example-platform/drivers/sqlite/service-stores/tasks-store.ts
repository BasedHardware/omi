// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)
import type { Database } from "bun:sqlite";

import {
  computeTasksRevision,
  tasksPreconditionHolds,
  type TasksApplyOutcome,
  type TasksRecord,
  type TasksStore,
  type TasksWriteOp,
} from "../../../apps/service/stores/tasks-store";
import { configureServiceStoreConnection } from "./connection";

interface StoredTaskRow {
  readonly record_id: string;
  readonly revision: string;
  readonly content_json: string | null;
  readonly first_seen_seq: number;
  readonly last_applied_seq: number;
  readonly live: number;
}

const toLiveRecord = (row: StoredTaskRow): TasksRecord => Object.freeze({
  record_id: row.record_id,
  revision: row.revision,
  content: Object.freeze(JSON.parse(row.content_json!) as Record<string, unknown>),
  first_seen_seq: row.first_seen_seq,
  last_applied_seq: row.last_applied_seq,
});

/** SQLite persistence adapter for the existing TasksStore port. */
export class SqliteTasksStore implements TasksStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_task_records (
        account_id TEXT NOT NULL,
        record_id TEXT NOT NULL,
        revision TEXT NOT NULL,
        content_json TEXT,
        first_seen_seq INTEGER NOT NULL,
        last_applied_seq INTEGER NOT NULL,
        live INTEGER NOT NULL CHECK (live IN (0, 1)),
        PRIMARY KEY (account_id, record_id),
        CHECK ((live = 1 AND content_json IS NOT NULL) OR (live = 0 AND content_json IS NULL))
      );
      CREATE TABLE IF NOT EXISTS service_task_apply_sequence (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT
      );
      CREATE INDEX IF NOT EXISTS service_task_records_by_account
        ON service_task_records (account_id, live);
      CREATE UNIQUE INDEX IF NOT EXISTS service_task_records_first_seen
        ON service_task_records (first_seen_seq);
    `);
  }

  listRecords(accountId: string): readonly TasksRecord[] {
    const rows = this.db.query(`
      SELECT record_id, revision, content_json, first_seen_seq, last_applied_seq, live
      FROM service_task_records
      WHERE account_id = ? AND live = 1
      ORDER BY first_seen_seq ASC
    `).all(accountId) as StoredTaskRow[];
    // The order key is a globally unique integer allocated by the store. SQL
    // never compares record ids, so text collation cannot become an authority.
    return Object.freeze(rows.map(toLiveRecord));
  }

  readRecord(accountId: string, recordId: string): TasksRecord | null {
    const row = this.db.query(`
      SELECT record_id, revision, content_json, first_seen_seq, last_applied_seq, live
      FROM service_task_records
      WHERE account_id = ? AND record_id = ? AND live = 1
    `).get(accountId, recordId) as StoredTaskRow | null;
    return row === null ? null : toLiveRecord(row);
  }

  apply(accountId: string, op: TasksWriteOp): TasksApplyOutcome {
    const apply = this.db.transaction((): TasksApplyOutcome => {
      const stored = this.db.query(`
        SELECT record_id, revision, content_json, first_seen_seq, last_applied_seq, live
        FROM service_task_records
        WHERE account_id = ? AND record_id = ?
      `).get(accountId, op.record_id) as StoredTaskRow | null;
      const current = stored !== null && stored.live === 1 ? toLiveRecord(stored) : undefined;
      const priorRevision = current?.revision ?? stored?.revision ?? null;
      const priorSeq = current?.first_seen_seq ?? stored?.first_seen_seq;

      if (op.op === "delete") {
        if (!tasksPreconditionHolds(current, op.base_revision)) {
          return { applied: false, reason: "conflict" };
        }
        if (current !== undefined) {
          this.db.query(`
            UPDATE service_task_records
            SET content_json = NULL, live = 0
            WHERE account_id = ? AND record_id = ?
          `).run(accountId, op.record_id);
        }
        return { applied: true, record_id: op.record_id, revision: null };
      }

      // The in-memory port consumes one sequence for every attempted non-delete,
      // including a failed patch precondition. Preserve that observable ordering.
      const allocated = this.db.query(
        "INSERT INTO service_task_apply_sequence DEFAULT VALUES",
      ).run();
      const sequence = Number(allocated.lastInsertRowid);

      if (op.op === "create") {
        const revision = computeTasksRevision(priorRevision, op.record_id, op.content);
        this.upsertLive(accountId, {
          record_id: op.record_id,
          revision,
          content: op.content,
          first_seen_seq: priorSeq ?? sequence,
          last_applied_seq: sequence,
        });
        return { applied: true, record_id: op.record_id, revision };
      }

      if (!tasksPreconditionHolds(current, op.base_revision)) {
        return { applied: false, reason: "conflict" };
      }
      const merged: Record<string, unknown> = {
        ...(current?.content ?? {}),
        ...op.patch,
      };
      const revision = computeTasksRevision(priorRevision, op.record_id, merged);
      this.upsertLive(accountId, {
        record_id: op.record_id,
        revision,
        content: merged,
        first_seen_seq: priorSeq ?? sequence,
        last_applied_seq: sequence,
      });
      return { applied: true, record_id: op.record_id, revision };
    });
    return apply.immediate();
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_task_records;");
      this.db.exec("DELETE FROM service_task_apply_sequence;");
      this.db.query("DELETE FROM sqlite_sequence WHERE name = ?").run("service_task_apply_sequence");
    });
    reset.immediate();
  }

  private upsertLive(accountId: string, row: TasksRecord): void {
    this.db.query(`
      INSERT INTO service_task_records (
        account_id, record_id, revision, content_json,
        first_seen_seq, last_applied_seq, live
      ) VALUES (?, ?, ?, ?, ?, ?, 1)
      ON CONFLICT (account_id, record_id) DO UPDATE SET
        revision = excluded.revision,
        content_json = excluded.content_json,
        first_seen_seq = excluded.first_seen_seq,
        last_applied_seq = excluded.last_applied_seq,
        live = 1
    `).run(
      accountId,
      row.record_id,
      row.revision,
      JSON.stringify(row.content),
      row.first_seen_seq,
      row.last_applied_seq,
    );
  }
}
