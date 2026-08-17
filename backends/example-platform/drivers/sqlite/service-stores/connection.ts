import type { Database } from "bun:sqlite";

/**
 * Connection policy shared by the local service adapters.
 *
 * WAL permits readers on a second connection while a writer is active.
 * `busy_timeout` bounds lock contention instead of failing the second writer
 * immediately. Read-modify-write methods additionally use `BEGIN IMMEDIATE`,
 * so two connections cannot both derive a new row from the same old state.
 */
export const configureServiceStoreConnection = (db: Database): void => {
  db.exec("PRAGMA busy_timeout = 5000;");
  db.query("PRAGMA journal_mode = WAL;").get();
  db.exec("PRAGMA foreign_keys = ON;");
};

