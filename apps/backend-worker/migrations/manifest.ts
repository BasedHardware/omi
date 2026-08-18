export interface D1MigrationManifestEntry {
  readonly version: number;
  readonly name: string;
  readonly fileName: string;
  readonly sha256: string;
}

export const D1_MIGRATIONS: readonly D1MigrationManifestEntry[] = Object.freeze(
  [
    Object.freeze({
      version: 1,
      name: "0001_tasks.sql",
      fileName: "0001_tasks.sql",
      sha256:
        "e9b4df967b8becc1406c35b5cfed4f893b4b0640cd0daa58ab37255e93fe12d1",
    }),
    Object.freeze({
      version: 2,
      name: "0002_chat.sql",
      fileName: "0002_chat.sql",
      sha256:
        "f1b3da76a9d949198e066af5320d2b684e32ecc4112896e8cd2ffdad75a824d1",
    }),
    Object.freeze({
      version: 3,
      name: "0003_attachments.sql",
      fileName: "0003_attachments.sql",
      sha256:
        "ee4efd8d61929ba0155753de9b6c5784f657b6264b90964c1c6dd34d9fc98fa3",
    }),
  ]
);
