export interface PostgresMigrationManifestEntry {
  readonly version: number;
  readonly name: string;
  readonly fileName: string;
  /** SHA-256 over the migration file's exact bytes. */
  readonly sha256: string;
}

export const POSTGRES_MIGRATIONS: readonly PostgresMigrationManifestEntry[] = Object.freeze([
  Object.freeze({
    version: 1,
    name: "account-control",
    fileName: "0001-account-control.sql",
    sha256: "086d58e5afc03fdad18665ba8c5b1c565960bb5b570f89704240cef531f3b5ff",
  }),
  Object.freeze({
    version: 2,
    name: "memory-ledger",
    fileName: "0002-memory-ledger.sql",
    sha256: "5081f78cce9b32b3e6c3258a838330fd57b4f031e4eff756e8c1fd6f54e14555",
  }),
  Object.freeze({
    version: 3,
    name: "formation-outcomes",
    fileName: "0003-formation-outcomes.sql",
    sha256: "527a619cb7739e0f9f858b528da800f48bfef2cd5963ecb83789beb22834ff15",
  }),
]);
