import type { Database } from "bun:sqlite";

import {
  RETENTION_CAP_SECONDS,
  type PreservedEnvelope,
  type StragglerTable,
} from "../../../apps/service/stores/straggler-table";
import { configureServiceStoreConnection } from "./connection";

interface StragglerRow extends PreservedEnvelope {
  readonly sequence: number;
}

const detached = (row: StragglerRow): PreservedEnvelope => Object.freeze({
  envelope_json: row.envelope_json,
  write_id: row.write_id,
  account_epoch: row.account_epoch,
  retained_at_epoch_seconds: row.retained_at_epoch_seconds,
});

/** SQLite persistence adapter for the existing StragglerTable port. */
export class SqliteStragglerTable implements StragglerTable {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_straggler_envelopes (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        envelope_json TEXT NOT NULL,
        write_id TEXT NOT NULL,
        account_epoch INTEGER NOT NULL,
        retained_at_epoch_seconds INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS service_straggler_envelopes_by_account
        ON service_straggler_envelopes (account_id, sequence);
      CREATE INDEX IF NOT EXISTS service_straggler_envelopes_by_retention
        ON service_straggler_envelopes (retained_at_epoch_seconds);
    `);
  }

  preserve(accountId: string, row: PreservedEnvelope): void {
    this.db.query(`
      INSERT INTO service_straggler_envelopes (
        account_id, envelope_json, write_id, account_epoch, retained_at_epoch_seconds
      ) VALUES (?, ?, ?, ?, ?)
    `).run(
      accountId,
      row.envelope_json,
      row.write_id,
      row.account_epoch,
      row.retained_at_epoch_seconds,
    );
  }

  exportAccount(accountId: string): readonly PreservedEnvelope[] {
    const rows = this.db.query(`
      SELECT sequence, envelope_json, write_id, account_epoch, retained_at_epoch_seconds
      FROM service_straggler_envelopes
      WHERE account_id = ?
      ORDER BY sequence ASC
    `).all(accountId) as StragglerRow[];
    return Object.freeze(rows.map(detached));
  }

  deleteAccount(accountId: string): number {
    return this.db.query(
      "DELETE FROM service_straggler_envelopes WHERE account_id = ?",
    ).run(accountId).changes;
  }

  sweepExpired(nowEpochSeconds: number): number {
    const horizon = nowEpochSeconds - RETENTION_CAP_SECONDS;
    return this.db.query(`
      DELETE FROM service_straggler_envelopes
      WHERE retained_at_epoch_seconds < ?
    `).run(horizon).changes;
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_straggler_envelopes;");
      this.db.query("DELETE FROM sqlite_sequence WHERE name = ?")
        .run("service_straggler_envelopes");
    });
    reset.immediate();
  }
}

