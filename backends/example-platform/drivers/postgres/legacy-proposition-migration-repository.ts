import { isProxy } from "node:util/types";

import {
  acceptLegacyMappingWinner,
  planLegacyPropositionMapping,
  type LegacyPropositionMapping,
} from "../../core/retrieve/product-projection";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import {
  defineLegacyPropositionMigrationRepository,
  type LegacyMigrationTombstoneOutcome,
  type LegacyPropositionMappingResumeOutcome,
  type LegacyPropositionMigrationRepository,
} from "../../apps/service/stores/legacy-proposition-migration-repository";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
  type PostgresTransactionObservability,
} from "./transaction";

interface ResumeRow extends Record<string, unknown> {
  readonly result_kind: string;
  readonly mapping_version: string | null;
  readonly owner_account_id: string | null;
  readonly legacy_source_id: string | null;
  readonly proposition_id: string | null;
  readonly content_hash: string | null;
}

interface TombstoneRow extends Record<string, unknown> {
  readonly result_kind: string;
  readonly request_digest: string;
}

const RESUME_SQL = `
SELECT * FROM omi_memory.resume_legacy_proposition_mapping($1, $2, $3, $4)
`;
const TOMBSTONE_SQL = `
SELECT * FROM omi_memory.record_legacy_migration_item_tombstone($1, $2, $3, $4, $5, $6)
`;
const DIGEST = /^[a-f0-9]{64}$/;

const exactRow = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) throw new PostgresRepositoryError("persistence_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.length !== keys.length || actual.some((key) => typeof key !== "string" || !keys.includes(key))) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const output: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      throw new PostgresRepositoryError("persistence_failed");
    }
    output[key] = descriptor.value;
  }
  return output;
};

const common = (
  error: PostgresRepositoryError,
): LegacyPropositionMappingResumeOutcome | LegacyMigrationTombstoneOutcome | null => {
  switch (error.code) {
    case "expired_context":
    case "stale_epoch":
    case "destination_inactive":
    case "lifecycle_inactive":
      return Object.freeze({ kind: "stale_context" as const, reason: error.code });
    case "credential_inactive":
    case "grant_inactive":
    case "capability_denied":
      return Object.freeze({ kind: "authorization_denied" as const, reason: error.code });
    case "idempotency_conflict":
      return Object.freeze({ kind: "idempotency_conflict" as const });
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    default:
      return null;
  }
};

const mappingFrom = (
  context: AuthorizedLedgerWriteContext,
  request: Readonly<{ legacy_source_id: string; proposed_random_opaque_proposition_id: string | null }>,
  value: unknown,
): LegacyPropositionMappingResumeOutcome => {
  const row = exactRow(value, [
    "result_kind", "mapping_version", "owner_account_id", "legacy_source_id",
    "proposition_id", "content_hash",
  ]);
  if (row["result_kind"] === "tombstoned" || row["result_kind"] === "allocation_required") {
    if (row["mapping_version"] !== null || row["owner_account_id"] !== null
      || row["legacy_source_id"] !== null || row["proposition_id"] !== null
      || row["content_hash"] !== null) throw new PostgresRepositoryError("persistence_failed");
    return Object.freeze({ kind: row["result_kind"] });
  }
  if (row["result_kind"] !== "inserted" && row["result_kind"] !== "reused") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const mappingPlan = planLegacyPropositionMapping({
    owner_account_id: context.account_id,
    legacy_source_id: request.legacy_source_id,
    item_tombstoned: false,
    existing_mapping: {
      version: row["mapping_version"],
      owner_account_id: row["owner_account_id"],
      legacy_source_id: row["legacy_source_id"],
      proposition_id: row["proposition_id"],
    } as LegacyPropositionMapping,
    proposed_random_opaque_proposition_id: null,
  });
  if (mappingPlan.kind !== "reuse_mapping" || typeof row["content_hash"] !== "string"
    || !DIGEST.test(row["content_hash"])
    || row["content_hash"] !== sha256CanonicalContent(mappingPlan.mapping)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (row["result_kind"] === "inserted") {
    if (request.proposed_random_opaque_proposition_id === null) {
      throw new PostgresRepositoryError("persistence_failed");
    }
    const attempted = planLegacyPropositionMapping({
      owner_account_id: context.account_id,
      legacy_source_id: request.legacy_source_id,
      item_tombstoned: false,
      existing_mapping: null,
      proposed_random_opaque_proposition_id: request.proposed_random_opaque_proposition_id,
    });
    if (attempted.kind !== "insert_if_absent"
      || acceptLegacyMappingWinner(attempted.mapping, mappingPlan.mapping).proposition_id
        !== attempted.mapping.proposition_id) throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({ kind: row["result_kind"], mapping: mappingPlan.mapping });
};

const resume = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: Readonly<{
    legacy_source_id: string;
    proposed_random_opaque_proposition_id: string | null;
    request_digest: string;
  }>,
  observability: PostgresTransactionObservability,
): Promise<LegacyPropositionMappingResumeOutcome> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection }) => {
        let mappingHash: string | null = null;
        if (request.proposed_random_opaque_proposition_id !== null) {
          const plan = planLegacyPropositionMapping({
            owner_account_id: authority.account_id,
            legacy_source_id: request.legacy_source_id,
            item_tombstoned: false,
            existing_mapping: null,
            proposed_random_opaque_proposition_id: request.proposed_random_opaque_proposition_id,
          });
          if (plan.kind !== "insert_if_absent") throw new PostgresRepositoryError("transition_invalid");
          mappingHash = sha256CanonicalContent(plan.mapping);
        }
        const rows = await connection.query<ResumeRow>({
          name: "legacy_migration.resume_mapping",
          text: RESUME_SQL,
          values: [authority.account_id, request.legacy_source_id,
            request.proposed_random_opaque_proposition_id, mappingHash],
        });
        if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
        return mappingFrom(authority, request, rows[0]);
      },
      observability,
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    const outcome = common(error);
    if (outcome) return outcome as LegacyPropositionMappingResumeOutcome;
    throw error;
  }
};

const recordTombstone = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: Readonly<{
    legacy_source_id: string;
    tombstone_sequence: number;
    tombstone_operation_id: string;
    tombstoned_at_event_time: number;
    request_digest: string;
  }>,
  observability: PostgresTransactionObservability,
): Promise<LegacyMigrationTombstoneOutcome> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection }) => {
        const rows = await connection.query<TombstoneRow>({
          name: "legacy_migration.record_tombstone",
          text: TOMBSTONE_SQL,
          values: [authority.account_id, request.legacy_source_id, request.tombstone_sequence,
            request.tombstone_operation_id, request.tombstoned_at_event_time, request.request_digest],
        });
        if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
        const row = exactRow(rows[0], ["result_kind", "request_digest"]);
        if ((row["result_kind"] !== "recorded" && row["result_kind"] !== "replayed")
          || row["request_digest"] !== request.request_digest) {
          throw new PostgresRepositoryError("persistence_failed");
        }
        return Object.freeze({ kind: row["result_kind"] });
      },
      observability,
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    const outcome = common(error);
    if (outcome) return outcome as LegacyMigrationTombstoneOutcome;
    throw error;
  }
};

export const createPostgresLegacyPropositionMigrationRepository = (options: {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}): LegacyPropositionMigrationRepository => defineLegacyPropositionMigrationRepository({
  resumeMapping: (context, request) => resume(
    options.pool, context, request, options.observability ?? {},
  ),
  recordTombstone: (context, request) => recordTombstone(
    options.pool, context, request, options.observability ?? {},
  ),
});
