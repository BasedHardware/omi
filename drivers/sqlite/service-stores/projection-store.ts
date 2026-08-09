import type { Database } from "bun:sqlite";

import {
  activateEpoch,
  admitObservation,
  deactivateEpoch,
  initialiseProjection,
  reconcileConflict,
  type AccountControlObservation,
  type AccountControlProjection,
  type ActivationResult,
  type AdmitObservationResult,
} from "../../../core/control/account-control";
import type { AccountControlProjectionStore } from "../../../apps/service/control/projection-store";
import { configureServiceStoreConnection } from "./connection";

const detachedProjection = (json: string): AccountControlProjection => {
  const value = JSON.parse(json) as AccountControlProjection;
  if (value.activation !== null) Object.freeze(value.activation);
  if (value.conflict !== null) Object.freeze(value.conflict);
  return Object.freeze(value);
};

/** SQLite persistence adapter for the existing AccountControlProjectionStore port. */
export class SqliteAccountControlProjectionStore implements AccountControlProjectionStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_account_control_projections (
        account_id TEXT PRIMARY KEY,
        projection_json TEXT NOT NULL
      );
    `);
  }

  read(accountId: string): AccountControlProjection | null {
    const row = this.db.query(`
      SELECT projection_json
      FROM service_account_control_projections
      WHERE account_id = ?
    `).get(accountId) as { projection_json: string } | null;
    return row === null ? null : detachedProjection(row.projection_json);
  }

  observe(observation: AccountControlObservation): AdmitObservationResult {
    const observe = this.db.transaction((): AdmitObservationResult => {
      const current = this.read(observation.account_id);
      const result = current === null
        ? initialiseProjection(observation)
        : admitObservation(current, observation);
      // Rejections that poison are state transitions and must be durable too.
      this.write(result.projection);
      return result;
    });
    return observe.immediate();
  }

  activate(
    accountId: string,
    request: { readonly epoch: number; readonly at_control_revision: number },
  ): ActivationResult {
    const activate = this.db.transaction((): ActivationResult => {
      const current = this.read(accountId);
      if (current === null) return { activated: false, reason: "no_account_epoch" };
      const result = activateEpoch(current, request);
      if (result.activated) this.write(result.projection);
      return result;
    });
    return activate.immediate();
  }

  deactivate(accountId: string): AccountControlProjection | null {
    const deactivate = this.db.transaction((): AccountControlProjection | null => {
      const current = this.read(accountId);
      if (current === null) return null;
      const next = deactivateEpoch(current);
      this.write(next);
      return next;
    });
    return deactivate.immediate();
  }

  forget(accountId: string): boolean {
    return this.db.query(`
      DELETE FROM service_account_control_projections
      WHERE account_id = ?
    `).run(accountId).changes > 0;
  }

  reconcile(
    observation: AccountControlObservation,
    operator: { readonly reason: string },
  ): AdmitObservationResult {
    const reconcile = this.db.transaction((): AdmitObservationResult => {
      const current = this.read(observation.account_id);
      // Match the existing in-memory adapter: reconciliation is an exit from a
      // poisoned row, not a bootstrap write for an unknown account.
      if (current === null) return initialiseProjection(observation);
      const result = reconcileConflict(current, observation, operator);
      if (result.accepted) this.write(result.projection);
      return result;
    });
    return reconcile.immediate();
  }

  private write(projection: AccountControlProjection): void {
    this.db.query(`
      INSERT INTO service_account_control_projections (account_id, projection_json)
      VALUES (?, ?)
      ON CONFLICT (account_id) DO UPDATE SET
        projection_json = excluded.projection_json
    `).run(projection.account_id, JSON.stringify(projection));
  }
}

