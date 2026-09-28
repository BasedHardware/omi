import type { Database } from "bun:sqlite";

import type { AccountLifecycleState } from "../../../core/control/account-control";
import {
  assertAccountLifecycleState,
  type AccountLifecycleStore,
} from "../../../apps/service/auth/account-lifecycle";
import { configureServiceStoreConnection } from "./connection";

/** SQLite QA adapter. Missing source state stays missing and fails closed. */
export class SqliteAccountLifecycleStore implements AccountLifecycleStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_account_lifecycle (
        account_id TEXT PRIMARY KEY,
        lifecycle_state TEXT NOT NULL
          CHECK (lifecycle_state IN ('active', 'deletion_pending', 'deleted'))
      );
    `);
  }

  readLifecycle(accountId: string): AccountLifecycleState | null {
    const row = this.db.query(`
      SELECT lifecycle_state
      FROM service_account_lifecycle
      WHERE account_id = ?
    `).get(accountId) as { readonly lifecycle_state: AccountLifecycleState } | null;
    return row === null ? null : assertAccountLifecycleState(row.lifecycle_state);
  }

  setLifecycle(accountId: string, state: AccountLifecycleState): void {
    const lifecycle = assertAccountLifecycleState(state);
    this.db.query(`
      INSERT INTO service_account_lifecycle (account_id, lifecycle_state)
      VALUES (?, ?)
      ON CONFLICT (account_id) DO UPDATE SET
        lifecycle_state = excluded.lifecycle_state
    `).run(accountId, lifecycle);
  }

  reset(): void {
    this.db.exec("DELETE FROM service_account_lifecycle;");
  }
}
