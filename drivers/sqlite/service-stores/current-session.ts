import type { Database } from "bun:sqlite";

import {
  digestSessionHandle,
  type CurrentSessionPort,
  type CurrentSessionRevocation,
  type DevTokenResolver,
} from "../../../apps/service/auth/current-session";
import type { DevPrincipal } from "../../../apps/service/auth/dev-token";
import { configureServiceStoreConnection } from "./connection";

/** SQLite dev-token revocation adapter. It persists digests, never credentials. */
export class SqliteCurrentSessionPort implements CurrentSessionPort {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_dev_token_revocations (
        token_digest TEXT PRIMARY KEY CHECK (length(token_digest) = 64)
      );
    `);
  }

  authenticate(token: string, resolveDevToken: DevTokenResolver): DevPrincipal | null {
    const revoked = this.db.query(`
      SELECT 1 AS present FROM service_dev_token_revocations WHERE token_digest = ?
    `).get(digestSessionHandle(token));
    return revoked === null ? resolveDevToken(token) : null;
  }

  revoke(token: string, resolveDevToken: DevTokenResolver): CurrentSessionRevocation {
    const revoke = this.db.transaction((): CurrentSessionRevocation => {
      const digest = digestSessionHandle(token);
      const revoked = this.db.query(`
        SELECT 1 AS present FROM service_dev_token_revocations WHERE token_digest = ?
      `).get(digest);
      if (revoked !== null) return Object.freeze({ status: "already_revoked" });
      if (resolveDevToken(token) === null) return Object.freeze({ status: "unrecognized" });
      this.db.query(`
        INSERT INTO service_dev_token_revocations (token_digest) VALUES (?)
      `).run(digest);
      return Object.freeze({ status: "revoked" });
    });
    return revoke.immediate();
  }
}
