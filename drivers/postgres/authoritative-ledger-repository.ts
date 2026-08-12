import {
  defineAuthoritativeLedgerRepository,
  type AuthoritativeLedgerAppend,
  type AuthoritativeLedgerAppendOutcome,
  type AuthoritativeLedgerRepository,
} from "../../apps/service/stores/authoritative-ledger-repository";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import { sha256CanonicalRedacted, type CanonicalJson } from "../../core/ledger";
import type { PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
  type PostgresTransactionObservability,
} from "./transaction";

interface ReceiptRow extends Record<string, unknown> {
  readonly request_digest: string;
  readonly state: "reserved" | "finalized";
  readonly commit_id: string | null;
  readonly sequence: string | number | bigint | null;
  readonly attempt_id: string | null;
  readonly parent_commit_id: string | null;
  readonly input_digest: string | null;
  readonly input_version_digest: string | null;
  readonly output_digest: string | null;
  readonly success_kind: string | null;
  readonly origin_kind: string | null;
  readonly formation_work_id: string | null;
  readonly non_formation_reason: string | null;
  readonly record_json: unknown;
}

interface HeadRow extends Record<string, unknown> {
  readonly commit_id: string | null;
  readonly sequence: string | number | bigint;
}

const supportedReason = new Set([
  "repair", "manual_liveness", "historical_replay",
] as const);
const jsonBytes = (value: unknown): Uint8Array => new TextEncoder().encode(JSON.stringify(value));

const safeCounter = (value: unknown): number => {
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value !== "string" && typeof value !== "number" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return number;
};

const assertQualificationTransition = (request: AuthoritativeLedgerAppend): void => {
  const transition = request.transition;
  const commit = transition.derivation.commit;
  if (request.origin.kind !== "non_formation" || !supportedReason.has(request.origin.reason as never)
    || commit.success_kind !== "successful_empty"
    || commit.input_revision_ids.length !== 0
    || commit.output_revision_ids.length !== 0
    || commit.output_revisions.length !== 0
    || transition.revisions.length !== 0
    || transition.adjacency.length !== 0
    || transition.artifacts.length !== 0
    || transition.placement.results.length !== 0
    || Object.keys(transition.placement.allocations).length !== 0
    || transition.committed_revisions !== undefined
    || transition.identity_authority_context !== undefined
    || transition.derived_identity_support !== undefined) {
    throw new PostgresRepositoryError("transition_invalid");
  }
};

const replayOutcome = (
  row: ReceiptRow,
  request: AuthoritativeLedgerAppend,
): AuthoritativeLedgerAppendOutcome => {
  if (row.request_digest !== request.append_attempt.request_digest) {
    return Object.freeze({ kind: "idempotency_conflict" as const });
  }
  const commit = request.transition.derivation.commit;
  const expectedRecord = { ...commit, sequence: safeCounter(row.sequence) };
  if (row.state !== "finalized" || typeof row.commit_id !== "string" || row.commit_id.length === 0
    || row.sequence === null
    || row.commit_id !== commit.commit_id
    || row.attempt_id !== commit.attempt_id
    || row.parent_commit_id !== commit.parent_commit
    || row.input_digest !== commit.input_digest
    || row.input_version_digest !== commit.input_version_digest
    || row.output_digest !== commit.output_digest
    || row.success_kind !== commit.success_kind
    || row.origin_kind !== "non_formation"
    || row.formation_work_id !== null
    || request.origin.kind !== "non_formation"
    || row.non_formation_reason !== request.origin.reason
    || row.record_json === null || typeof row.record_json !== "object" || Array.isArray(row.record_json)
    || sha256CanonicalRedacted(row.record_json as CanonicalJson)
      !== sha256CanonicalRedacted(expectedRecord as unknown as CanonicalJson)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({
    kind: "replayed" as const,
    commit_id: row.commit_id,
    sequence: safeCounter(row.sequence),
  });
};

const appendSuccessfulEmpty = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: AuthoritativeLedgerAppend,
  observability: PostgresTransactionObservability,
): Promise<AuthoritativeLedgerAppendOutcome> => {
  assertQualificationTransition(request);
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection }) => {
        const attempt = request.append_attempt;
        const derivation = request.transition.derivation;
        const commit = derivation.commit;
        const receiptValues = [authority.account_id, authority.account_epoch, attempt.idempotency_key] as const;
        const receipts = await connection.query<ReceiptRow>({
          name: "ledger.receipt_lookup",
          text: `
SELECT r.request_digest, r.state, r.commit_id, c.sequence,
       c.attempt_id, c.parent_commit_id, c.input_digest,
       c.input_version_digest, c.output_digest, c.success_kind,
       c.origin_kind, c.formation_work_id, c.non_formation_reason,
       c.record_json
FROM omi_memory.memory_idempotency_receipts AS r
LEFT JOIN omi_memory.memory_derivation_commits AS c
  ON c.account_id = r.account_id AND c.commit_id = r.commit_id
WHERE r.account_id = $1 AND r.account_epoch = $2 AND r.idempotency_key = $3
FOR UPDATE OF r
`,
          values: receiptValues,
        });
        if (receipts.length > 1) throw new PostgresRepositoryError("persistence_failed");
        if (receipts[0]) return replayOutcome(receipts[0], request);

        const reserved = await connection.execute({
          name: "ledger.receipt_reserve",
          text: `
INSERT INTO omi_memory.memory_idempotency_receipts
  (account_id, account_epoch, idempotency_key, request_digest, state)
VALUES ($1, $2, $3, $4, 'reserved')
ON CONFLICT (account_id, account_epoch, idempotency_key) DO NOTHING
`,
          values: [...receiptValues, attempt.request_digest],
        });
        if (reserved.rowCount !== 1) {
          // Another SERIALIZABLE writer won the key after our snapshot.  A
          // caller retry revalidates authority and observes its exact receipt.
          throw new PostgresRepositoryError("retryable_serialization", true);
        }

        const heads = await connection.query<HeadRow>({
          name: "ledger.head_lock",
          text: `
SELECT commit_id, sequence
FROM omi_memory.memory_graph_heads
WHERE account_id = $1
FOR UPDATE
`,
          values: [authority.account_id],
        });
        const head = heads[0];
        if (heads.length !== 1 || !head) throw new PostgresRepositoryError("persistence_failed");
        const headSequence = safeCounter(head.sequence);
        if (head.commit_id !== attempt.expected_parent_commit) {
          throw new PostgresRepositoryError("stale_parent");
        }
        const sequence = headSequence + 1;
        if (!Number.isSafeInteger(sequence)) throw new PostgresRepositoryError("persistence_failed");

        await connection.execute({
          name: "ledger.attempt_insert",
          text: `
INSERT INTO omi_memory.memory_derivation_attempts
  (account_id, attempt_id, input_digest, input_version_digest, output_digest,
   success_kind, versions, record_json)
VALUES ($1, $2, $3, $4, $5, $6,
        convert_from($7::bytea, 'UTF8')::jsonb,
        convert_from($8::bytea, 'UTF8')::jsonb)
`,
          values: [
            authority.account_id,
            derivation.attempt.attempt_id,
            derivation.attempt.input_digest,
            derivation.attempt.input_version_digest,
            derivation.attempt.output_digest,
            derivation.attempt.success_kind,
            jsonBytes(derivation.attempt.versions),
            jsonBytes(derivation.attempt),
          ],
        });

        const commitRecord = { ...commit, sequence };
        await connection.execute({
          name: "ledger.commit_insert",
          text: `
INSERT INTO omi_memory.memory_derivation_commits
  (account_id, commit_id, attempt_id, parent_commit_id, sequence,
   input_digest, input_version_digest, output_digest, success_kind,
   origin_kind, formation_work_id, non_formation_reason, record_json)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
        'non_formation', NULL, $10, convert_from($11::bytea, 'UTF8')::jsonb)
`,
          values: [
            authority.account_id,
            commit.commit_id,
            commit.attempt_id,
            commit.parent_commit,
            sequence,
            commit.input_digest,
            commit.input_version_digest,
            commit.output_digest,
            commit.success_kind,
            request.origin.kind === "non_formation" ? request.origin.reason : "repair",
            jsonBytes(commitRecord),
          ],
        });

        const advanced = await connection.execute({
          name: "ledger.head_advance",
          text: `
UPDATE omi_memory.memory_graph_heads
SET commit_id = $2, sequence = $3, updated_at = transaction_timestamp()
WHERE account_id = $1 AND sequence = $4
  AND commit_id IS NOT DISTINCT FROM $5
`,
          values: [authority.account_id, commit.commit_id, sequence, headSequence, head.commit_id],
        });
        if (advanced.rowCount !== 1) throw new PostgresRepositoryError("stale_parent");

        const finalized = await connection.execute({
          name: "ledger.receipt_finalize",
          text: `
UPDATE omi_memory.memory_idempotency_receipts
SET state = 'finalized', commit_id = $4, finalized_at = transaction_timestamp()
WHERE account_id = $1 AND account_epoch = $2 AND idempotency_key = $3
  AND request_digest = $5 AND state = 'reserved' AND commit_id IS NULL
`,
          values: [
            authority.account_id,
            authority.account_epoch,
            attempt.idempotency_key,
            commit.commit_id,
            attempt.request_digest,
          ],
        });
        if (finalized.rowCount !== 1) throw new PostgresRepositoryError("persistence_failed");
        return Object.freeze({ kind: "committed" as const, commit_id: commit.commit_id, sequence });
      },
      observability,
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    switch (error.code) {
      case "expired_context":
      case "stale_epoch":
      case "destination_inactive":
      case "lifecycle_inactive":
        return Object.freeze({ kind: "stale_context" as const, reason: error.code });
      case "credential_inactive":
        return Object.freeze({ kind: "authorization_denied" as const, reason: "credential_inactive" as const });
      case "grant_inactive":
        return Object.freeze({ kind: "authorization_denied" as const, reason: "grant_inactive" as const });
      case "capability_denied":
        return Object.freeze({ kind: "authorization_denied" as const, reason: "capability_denied" as const });
      case "idempotency_conflict":
        return Object.freeze({ kind: "idempotency_conflict" as const });
      case "stale_parent":
        return Object.freeze({ kind: "stale_parent" as const });
      case "retryable_serialization":
        return Object.freeze({ kind: "serialization_retryable" as const });
      default:
        throw error;
    }
  }
};

export interface PostgresSuccessfulEmptyLedgerRepositoryOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/**
 * Qualification-only persistence kernel for input-empty/output-empty,
 * successful-empty legacy maintenance commits.  It deliberately rejects all
 * graph revisions, formation work, durable-job origins, and service wiring.
 * It is not the canonical PostgreSQL repository and must be replaced or
 * expanded before activation.
 */
export const createPostgresSuccessfulEmptyLedgerRepository = (
  options: PostgresSuccessfulEmptyLedgerRepositoryOptions,
): AuthoritativeLedgerRepository => defineAuthoritativeLedgerRepository(
  (context, request) => appendSuccessfulEmpty(
    options.pool,
    context,
    request,
    options.observability ?? {},
  ),
);
