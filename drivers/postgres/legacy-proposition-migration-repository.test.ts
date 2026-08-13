import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  defineLegacyPropositionMigrationRepository,
  legacyMigrationTombstoneRequestDigest,
  legacyPropositionMappingResumeRequestDigest,
  type LegacyMigrationTombstoneBody,
  type LegacyPropositionMappingResumeBody,
} from "../../apps/service/stores/legacy-proposition-migration-repository";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { createPostgresLegacyPropositionMigrationRepository } from
  "./legacy-proposition-migration-repository";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const hex = (character: string): string => character.repeat(64);
const authority = (): AuthorityStateRow => ({
  account_id: "account:alice", principal_id: "principal:alice", application_id: "app:projector",
  credential_id: "credential:projector", credential_generation: 4, capability: "memories.project",
  grant_id: "grant:projector", grant_version: 9, account_epoch: 12,
  control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 12, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 300,
  control_revision: 17, control_content_hash: hex("1"), credential_content_hash: hex("2"),
  grant_content_hash: hex("3"), db_now_epoch_seconds: 150,
});
const context = (capability = "memories.project") => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1", principal_id: "principal:alice",
  account_id: "account:alice", application_id: "app:projector",
  credential_id: "credential:projector", credential_generation: 4, capability,
  grant_id: "grant:projector", grant_version: 9, account_epoch: 12,
  destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
  authentication_strength: "service-workload", issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200, authorization_state_digest: authorizationStateDigest(authority()),
}, 150);

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "legacy-migration" });
  readonly statements: SqlStatement[] = [];
  constructor(readonly rows: Record<string, readonly Record<string, unknown>[]>) {}
  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") return [authority() as unknown as Row];
    return (this.rows[statement.name] ?? []) as readonly Row[];
  }
  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    return { rowCount: 1 };
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];
  constructor(readonly connection: FakeConnection) {}
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.options.push(options);
    return callback(this.connection);
  }
}

const resume = (proposed: string | null = "proposition:opaque:7d958246") => {
  const body: LegacyPropositionMappingResumeBody = {
    legacy_source_id: "legacy:item:42", proposed_random_opaque_proposition_id: proposed,
  };
  return { ...body, request_digest: legacyPropositionMappingResumeRequestDigest("account:alice", body) };
};
const tombstone = (overrides: Partial<LegacyMigrationTombstoneBody> = {}) => {
  const body: LegacyMigrationTombstoneBody = {
    legacy_source_id: "legacy:item:42", tombstone_sequence: 3,
    tombstone_operation_id: "migration-tombstone:42", tombstoned_at_event_time: 170,
    ...overrides,
  };
  return { ...body, request_digest: legacyMigrationTombstoneRequestDigest("account:alice", body) };
};
const mappingRow = (resultKind: "inserted" | "reused") => {
  const mapping = {
    version: "product-projection-v1", owner_account_id: "account:alice",
    legacy_source_id: "legacy:item:42", proposition_id: "proposition:opaque:7d958246",
  };
  return {
    result_kind: resultKind, mapping_version: mapping.version,
    owner_account_id: mapping.owner_account_id, legacy_source_id: mapping.legacy_source_id,
    proposition_id: mapping.proposition_id, content_hash: sha256CanonicalContent(mapping),
  };
};

describe("PostgreSQL legacy proposition migration repository", () => {
  test("revalidates authority then inserts or reuses the durable mapping winner", async () => {
    for (const kind of ["inserted", "reused"] as const) {
      const connection = new FakeConnection({ "legacy_migration.resume_mapping": [mappingRow(kind)] });
      const repository = createPostgresLegacyPropositionMigrationRepository({ pool: new FakePool(connection) });
      await expect(repository.resumeMapping(context(), resume())).resolves.toEqual({
        kind, mapping: {
          version: "product-projection-v1", owner_account_id: "account:alice",
          legacy_source_id: "legacy:item:42", proposition_id: "proposition:opaque:7d958246",
        },
      });
      expect(connection.statements.map((statement) => statement.name)).toEqual([
        "authority.set_local", "authority.lock_and_revalidate", "legacy_migration.resume_mapping",
      ]);
      expect(connection.statements.at(-1)?.values.slice(0, 3)).toEqual([
        "account:alice", "legacy:item:42", "proposition:opaque:7d958246",
      ]);
    }
  });

  test("keeps allocation-required and tombstoned outcomes mapping-free", async () => {
    for (const kind of ["allocation_required", "tombstoned"] as const) {
      const row = {
        result_kind: kind, mapping_version: null, owner_account_id: null,
        legacy_source_id: null, proposition_id: null, content_hash: null,
      };
      const repository = createPostgresLegacyPropositionMigrationRepository({
        pool: new FakePool(new FakeConnection({ "legacy_migration.resume_mapping": [row] })),
      });
      await expect(repository.resumeMapping(context(), resume(null))).resolves.toEqual({ kind });
    }
  });

  test("records and replays an exact tombstone through the same authority transaction", async () => {
    const request = tombstone();
    for (const kind of ["recorded", "replayed"] as const) {
      const connection = new FakeConnection({
        "legacy_migration.record_tombstone": [{ result_kind: kind, request_digest: request.request_digest }],
      });
      const repository = createPostgresLegacyPropositionMigrationRepository({ pool: new FakePool(connection) });
      await expect(repository.recordTombstone(context(), request)).resolves.toEqual({ kind });
      expect(connection.statements.map((statement) => statement.name)).toEqual([
        "authority.set_local", "authority.lock_and_revalidate", "legacy_migration.record_tombstone",
      ]);
    }
  });

  test("rejects wrong authority, changed digests, corrupt rows, and accessors before unsafe use", async () => {
    const connection = new FakeConnection({ "legacy_migration.resume_mapping": [mappingRow("inserted")] });
    const repository = createPostgresLegacyPropositionMigrationRepository({ pool: new FakePool(connection) });
    await expect(repository.resumeMapping(context("memories.read"), resume())).rejects.toThrow("capability_denied");
    expect(connection.statements).toHaveLength(0);
    await expect(repository.resumeMapping(context(), { ...resume(), request_digest: hex("f") }))
      .rejects.toThrow("invalid_resume_request");
    expect(connection.statements).toHaveLength(0);
    const hostile = Object.defineProperty(mappingRow("inserted"), "content_hash", {
      enumerable: true, get() { throw new Error("must not execute"); },
    });
    const hostileRepository = createPostgresLegacyPropositionMigrationRepository({
      pool: new FakePool(new FakeConnection({ "legacy_migration.resume_mapping": [hostile] })),
    });
    await expect(hostileRepository.resumeMapping(context(), resume())).rejects.toThrow("persistence_failed");
  });

  test("the sealed service port rejects forged implementation outcomes", async () => {
    const forgedMapping = defineLegacyPropositionMigrationRepository({
      async resumeMapping() {
        return {
          kind: "inserted",
          mapping: {
            version: "product-projection-v1", owner_account_id: "account:bob",
            legacy_source_id: "legacy:item:42", proposition_id: "proposition:opaque:7d958246",
          },
        };
      },
      async recordTombstone() { return { kind: "recorded", extra: true }; },
    });
    await expect(forgedMapping.resumeMapping(context(), resume()))
      .rejects.toThrow("invalid_migration_mapping");
    await expect(forgedMapping.recordTombstone(context(), tombstone()))
      .rejects.toThrow("invalid_tombstone_outcome");
  });
});
