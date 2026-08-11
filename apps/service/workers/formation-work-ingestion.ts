import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  type AcceptedDurableMemoryWork,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
} from "../../../core/consolidate/strategy-assignment";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceOutcome,
  type DurableMemoryWorkAcceptanceRepository,
} from "../stores/durable-memory-work-repository";
import {
  formationWorkInputManifest,
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "./formation-work-producer";

const INGESTION_PORT: unique symbol = Symbol("formation-work-ingestion");

export interface FormationWorkIngestionRequest {
  readonly snapshot: FormationInputSnapshot;
  readonly strategy_assignment: Readonly<MemoryStrategyAssignmentBundle>;
  readonly accepted_at_event_time: number;
  readonly max_attempts: number;
}

export type FormationWorkIngestionOutcome = DurableMemoryWorkAcceptanceOutcome;

export interface FormationWorkIngestion {
  readonly [INGESTION_PORT]: true;
  accept(
    context: AuthorizedLedgerWriteContext,
    request: FormationWorkIngestionRequest,
  ): Promise<FormationWorkIngestionOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`formation work ingestion ${code}`); };

const acceptedWork = (
  context: AuthorizedLedgerWriteContext,
  snapshot: Readonly<FormationInputSnapshot>,
  assignment: Readonly<MemoryStrategyAssignmentBundle>,
  acceptedAt: number,
  maxAttempts: number,
): AcceptedDurableMemoryWork => {
  if (!Number.isSafeInteger(acceptedAt) || acceptedAt < 0
    || !Number.isSafeInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 100) {
    fail("invalid_schedule");
  }
  if (assignment.owner_account_id !== snapshot.owner_account_id
    || assignment.work_kind !== "formation"
    || assignment.authority.mode !== "authority"
    || context.account_id !== snapshot.owner_account_id
    || context.account_epoch < 0) fail("coordinate_mismatch");
  const manifest = formationWorkInputManifest(snapshot);
  return Object.freeze({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: snapshot.work_id,
    owner_account_id: snapshot.owner_account_id,
    account_epoch: context.account_epoch,
    lifecycle_state: "active" as const,
    deletion_epoch: null,
    work_kind: "formation" as const,
    input_frontier: snapshot.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(manifest),
    execution_contract_digest: assignment.authority.execution_contract_digest,
    accepted_at_event_time: acceptedAt,
    max_attempts: maxAttempts,
  });
};

export const defineFormationWorkIngestion = (
  repository: DurableMemoryWorkAcceptanceRepository,
): FormationWorkIngestion => Object.freeze({
  [INGESTION_PORT]: true as const,
  async accept(
    contextValue: AuthorizedLedgerWriteContext,
    requestValue: FormationWorkIngestionRequest,
  ) {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    if (context.capability !== "memories.work.accept") fail("capability_denied");
    const snapshot = parseFormationInputSnapshot(requestValue.snapshot);
    const assignment = assertMintedMemoryStrategyAssignment(requestValue.strategy_assignment);
    const accepted = acceptedWork(
      context,
      snapshot,
      assignment,
      requestValue.accepted_at_event_time,
      requestValue.max_attempts,
    );
    const manifest = formationWorkInputManifest(snapshot);
    const pending: Readonly<DurableMemoryWorkJob> = acceptDurableMemoryWork(accepted);
    return repository.accept(context, {
      accepted_work: accepted,
      input_manifest: manifest,
      strategy_assignment: assignment,
      request_digest: durableMemoryWorkAcceptanceRequestDigest(pending, manifest, assignment),
    });
  },
});
