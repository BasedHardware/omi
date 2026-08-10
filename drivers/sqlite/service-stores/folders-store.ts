import type { Database } from "bun:sqlite";

import type {
  FolderCreateInput,
  FolderCreateOutcome,
  FolderPatch,
  FolderPatchOutcome,
  FolderRecord,
  FoldersStore,
} from "../../../apps/service/stores/folders-store";
import { configureServiceStoreConnection } from "./connection";

interface StoredFolderRow {
  readonly id: string;
  readonly name_json: string;
  readonly description_json: string;
  readonly color_json: string;
  readonly icon_json: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly order_json: string;
  readonly is_default: number;
  readonly is_system: number;
}

const decode = (value: string): unknown => JSON.parse(value) as unknown;
const encode = (value: unknown): string => JSON.stringify(value);

const toRecord = (row: StoredFolderRow): FolderRecord => Object.freeze({
  id: row.id,
  name: decode(row.name_json),
  description: decode(row.description_json),
  color: decode(row.color_json),
  icon: decode(row.icon_json),
  created_at: row.created_at,
  updated_at: row.updated_at,
  order: decode(row.order_json),
  is_default: row.is_default === 1,
  is_system: row.is_system === 1,
});

const SELECT_FIELDS = `
  id, name_json, description_json, color_json, icon_json,
  created_at, updated_at, order_json, is_default, is_system
`;

/** SQLite persistence adapter for the FoldersStore port. */
export class SqliteFoldersStore implements FoldersStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_folder_records (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        id TEXT NOT NULL,
        name_json TEXT NOT NULL,
        description_json TEXT NOT NULL,
        color_json TEXT NOT NULL,
        icon_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        order_json TEXT NOT NULL,
        is_default INTEGER NOT NULL CHECK (is_default IN (0, 1)),
        is_system INTEGER NOT NULL CHECK (is_system IN (0, 1)),
        UNIQUE (account_id, id)
      );
      CREATE INDEX IF NOT EXISTS service_folder_records_by_account
        ON service_folder_records (account_id, sequence);
    `);
  }

  listFolders(accountId: string): readonly FolderRecord[] {
    const rows = this.db.query(`
      SELECT ${SELECT_FIELDS}
      FROM service_folder_records
      WHERE account_id = ?
      ORDER BY sequence ASC
    `).all(accountId) as StoredFolderRow[];
    return Object.freeze(rows.map(toRecord));
  }

  readFolder(accountId: string, folderId: string): FolderRecord | null {
    const row = this.db.query(`
      SELECT ${SELECT_FIELDS}
      FROM service_folder_records
      WHERE account_id = ? AND id = ?
    `).get(accountId, folderId) as StoredFolderRow | null;
    return row === null ? null : toRecord(row);
  }

  hasFolder(accountId: string, folderId: string): boolean {
    return this.readFolder(accountId, folderId) !== null;
  }

  upsert(accountId: string, record: FolderRecord): FolderRecord {
    const write = this.db.transaction(() => {
      this.db.query(`
        INSERT INTO service_folder_records (
          account_id, id, name_json, description_json, color_json, icon_json,
          created_at, updated_at, order_json, is_default, is_system
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (account_id, id) DO UPDATE SET
          name_json = excluded.name_json,
          description_json = excluded.description_json,
          color_json = excluded.color_json,
          icon_json = excluded.icon_json,
          created_at = excluded.created_at,
          updated_at = excluded.updated_at,
          order_json = excluded.order_json,
          is_default = excluded.is_default,
          is_system = excluded.is_system
      `).run(
        accountId, record.id, encode(record.name), encode(record.description),
        encode(record.color), encode(record.icon), record.created_at, record.updated_at,
        encode(record.order), record.is_default ? 1 : 0, record.is_system ? 1 : 0,
      );
      return this.readFolder(accountId, record.id)!;
    });
    return write.immediate();
  }

  createFolder(accountId: string, input: FolderCreateInput): FolderCreateOutcome {
    const write = this.db.transaction((): FolderCreateOutcome => {
      if (this.hasFolder(accountId, input.id)) {
        return { created: false, reason: "already_exists" };
      }
      const count = this.db.query(`
        SELECT COUNT(*) AS count FROM service_folder_records WHERE account_id = ?
      `).get(accountId) as { readonly count: number };
      const record: FolderRecord = {
        ...input,
        order: count.count,
        is_default: false,
        is_system: false,
      };
      return { created: true, record: this.upsert(accountId, record) };
    });
    return write.immediate();
  }

  patchFolder(
    accountId: string,
    folderId: string,
    patch: FolderPatch,
    updatedAt: string,
  ): FolderPatchOutcome {
    const write = this.db.transaction((): FolderPatchOutcome => {
      const current = this.readFolder(accountId, folderId);
      if (current === null) return { updated: false, reason: "not_found" };
      const record = this.upsert(accountId, {
        ...current,
        ...patch,
        updated_at: updatedAt,
      });
      return { updated: true, record };
    });
    return write.immediate();
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_folder_records;");
      this.db.query("DELETE FROM sqlite_sequence WHERE name = ?").run("service_folder_records");
    });
    reset.immediate();
  }
}
