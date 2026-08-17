import { createHash } from "node:crypto";
import type { Database } from "bun:sqlite";

import {
  exceedsFingerprintDepth,
  stableSerialize,
  type RecordedWriteOutcome,
  type WriteIdLookup,
  type WriteIdRegistry,
} from "../../../apps/service/stores/write-id-registry";
import { configureServiceStoreConnection } from "./connection";

interface RegistryRow {
  readonly fingerprint: string;
  readonly outcome_record_id: string;
  readonly outcome_revision: string | null;
}

const fingerprint = (value: unknown): string => {
  if (exceedsFingerprintDepth(value)) {
    throw new TypeError("write-id registry: value nests deeper than MAX_FINGERPRINT_DEPTH");
  }
  return createHash("sha256").update(stableSerialize(value), "utf8").digest("hex");
};

const outcomeOf = (row: RegistryRow): RecordedWriteOutcome => Object.freeze({
  record_id: row.outcome_record_id,
  revision: row.outcome_revision,
});

/** SQLite persistence adapter for the existing WriteIdRegistry port. */
export class SqliteWriteIdRegistry implements WriteIdRegistry {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_write_id_registry (
        account_id TEXT NOT NULL,
        write_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        account_epoch INTEGER NOT NULL,
        outcome_record_id TEXT NOT NULL,
        outcome_revision TEXT,
        PRIMARY KEY (account_id, write_id)
      );
      CREATE INDEX IF NOT EXISTS service_write_id_registry_by_epoch
        ON service_write_id_registry (account_id, account_epoch);
    `);
  }

  lookup(accountId: string, writeId: string, fingerprintOf: unknown): WriteIdLookup {
    const row = this.db.query(`
      SELECT fingerprint, outcome_record_id, outcome_revision
      FROM service_write_id_registry
      WHERE account_id = ? AND write_id = ?
    `).get(accountId, writeId) as RegistryRow | null;
    if (row === null) return { kind: "fresh" };
    return row.fingerprint === fingerprint(fingerprintOf)
      ? { kind: "replay", outcome: outcomeOf(row) }
      : { kind: "reuse" };
  }

  record(input: {
    readonly accountId: string;
    readonly writeId: string;
    readonly fingerprintOf: unknown;
    readonly accountEpoch: number;
    readonly outcome: RecordedWriteOutcome;
  }): void {
    this.db.query(`
      INSERT INTO service_write_id_registry (
        account_id, write_id, fingerprint, account_epoch,
        outcome_record_id, outcome_revision
      ) VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT (account_id, write_id) DO UPDATE SET
        fingerprint = excluded.fingerprint,
        account_epoch = excluded.account_epoch,
        outcome_record_id = excluded.outcome_record_id,
        outcome_revision = excluded.outcome_revision
    `).run(
      input.accountId,
      input.writeId,
      fingerprint(input.fingerprintOf),
      input.accountEpoch,
      input.outcome.record_id,
      input.outcome.revision,
    );
  }

  collectBelowEpoch(accountId: string, activeEpoch: number): number {
    return this.db.query(`
      DELETE FROM service_write_id_registry
      WHERE account_id = ? AND account_epoch < ?
    `).run(accountId, activeEpoch).changes;
  }

  size(accountId: string): number {
    const row = this.db.query(`
      SELECT COUNT(*) AS count
      FROM service_write_id_registry
      WHERE account_id = ?
    `).get(accountId) as { count: number };
    return row.count;
  }

  reset(): void {
    this.db.exec("DELETE FROM service_write_id_registry;");
  }
}

