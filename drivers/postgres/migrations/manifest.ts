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
  Object.freeze({
    version: 4,
    name: "durable-memory-work",
    fileName: "0004-durable-memory-work.sql",
    sha256: "053a19ddc283152162b2a67bd2a48f04ca0e4a42b3611ca0a86dd1d858e9a8d8",
  }),
  Object.freeze({
    version: 5,
    name: "product-memory-projections",
    fileName: "0005-product-memory-projections.sql",
    sha256: "8bfc7384fdfdea00973981a8dd1f0c5e2513d0343481d7da7c9acc49c8f651d6",
  }),
]);
