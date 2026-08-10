// domain-pending(UNK-DOMAPPS-001)
import type { Database } from "bun:sqlite";

import {
  detachedEntitlement,
  type SettingsEntitlementProjection,
  type SettingsIdentityProjection,
  type SettingsProjectionRead,
  type SettingsProjectionStore,
} from "../../../apps/service/control/settings-projection";
import { configureServiceStoreConnection } from "./connection";

type IdentityRow = { readonly display_name: string; readonly email: string };
type EntitlementRow = {
  readonly plan_label: string;
  readonly limit_key: string;
  readonly used: number;
  readonly limit_value: number | null;
  readonly limit_reached: number;
  readonly upgrade_available: number;
};

const identityFromRow = (row: IdentityRow): SettingsIdentityProjection => Object.freeze({
  displayName: row.display_name,
  email: row.email,
});

const entitlementFromRow = (row: EntitlementRow): SettingsEntitlementProjection =>
  detachedEntitlement({
    planLabel: row.plan_label,
    limitKey: row.limit_key,
    used: row.used,
    limit: row.limit_value,
    limitReached: row.limit_reached === 1,
    upgradeAvailable: row.upgrade_available === 1,
  });

/** SQLite adapter for coherent Settings and enforcement projection reads. */
export class SqliteSettingsProjectionStore implements SettingsProjectionStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_settings_identity_projections (
        account_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        email TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS service_settings_entitlement_projections (
        account_id TEXT PRIMARY KEY,
        plan_label TEXT NOT NULL,
        limit_key TEXT NOT NULL,
        used REAL NOT NULL CHECK (used >= 0),
        limit_value REAL CHECK (limit_value IS NULL OR limit_value >= 0),
        limit_reached INTEGER NOT NULL CHECK (limit_reached IN (0, 1)),
        upgrade_available INTEGER NOT NULL CHECK (upgrade_available IN (0, 1)),
        CHECK (limit_value IS NOT NULL OR limit_reached = 0)
      );
    `);
  }

  putIdentity(accountId: string, projection: SettingsIdentityProjection): void {
    if (typeof projection.displayName !== "string" || typeof projection.email !== "string") {
      throw new TypeError("invalid settings identity projection");
    }
    this.db.query(`
      INSERT INTO service_settings_identity_projections (account_id, display_name, email)
      VALUES (?, ?, ?)
      ON CONFLICT (account_id) DO UPDATE SET
        display_name = excluded.display_name,
        email = excluded.email
    `).run(accountId, projection.displayName, projection.email);
  }

  putEntitlement(accountId: string, projection: SettingsEntitlementProjection | null): void {
    if (projection === null) {
      this.db.query(`
        DELETE FROM service_settings_entitlement_projections WHERE account_id = ?
      `).run(accountId);
      return;
    }
    const detached = detachedEntitlement(projection);
    this.db.query(`
      INSERT INTO service_settings_entitlement_projections (
        account_id, plan_label, limit_key, used, limit_value,
        limit_reached, upgrade_available
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (account_id) DO UPDATE SET
        plan_label = excluded.plan_label,
        limit_key = excluded.limit_key,
        used = excluded.used,
        limit_value = excluded.limit_value,
        limit_reached = excluded.limit_reached,
        upgrade_available = excluded.upgrade_available
    `).run(
      accountId,
      detached.planLabel,
      detached.limitKey,
      detached.used,
      detached.limit,
      detached.limitReached ? 1 : 0,
      detached.upgradeAvailable ? 1 : 0,
    );
  }

  readEntitlement(accountId: string): SettingsEntitlementProjection | null {
    const row = this.db.query(`
      SELECT plan_label, limit_key, used, limit_value, limit_reached, upgrade_available
      FROM service_settings_entitlement_projections
      WHERE account_id = ?
    `).get(accountId) as EntitlementRow | null;
    return row === null ? null : entitlementFromRow(row);
  }

  readSettings(accountId: string): SettingsProjectionRead {
    const read = this.db.transaction((): SettingsProjectionRead => {
      const identityRow = this.db.query(`
        SELECT display_name, email
        FROM service_settings_identity_projections
        WHERE account_id = ?
      `).get(accountId) as IdentityRow | null;
      if (identityRow === null) return Object.freeze({ status: "unavailable" });
      return Object.freeze({
        status: "available",
        snapshot: Object.freeze({
          identity: identityFromRow(identityRow),
          entitlement: this.readEntitlement(accountId),
        }),
      });
    });
    return read.deferred();
  }
}
