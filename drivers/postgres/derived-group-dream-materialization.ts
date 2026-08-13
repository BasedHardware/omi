import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type { DurableMemoryWorkSuccessRequest } from "../../apps/service/stores/durable-memory-work-success-repository";
import type { CheckedOutPostgresConnection } from "./connection";
import { PostgresRepositoryError } from "./transaction";

export const persistDerivedGroupDreamMaterializationWithinTransaction = async (
  connection: CheckedOutPostgresConnection,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkSuccessRequest,
  graphCommitId: string,
  graphSequence: number,
): Promise<void> => {
  if (request.leased_job.work_kind !== "derived_group_dream") return;
  if (request.result_kind !== "successful" || graphCommitId.length === 0 || graphSequence < 1) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  await connection.execute({
    name: "derived-group-dream.materialization.persist",
    text: `
SELECT omi_memory.persist_derived_group_dream_materialization(
  $1, $2, $3, $4, $5, ($6::text)::jsonb
)
`,
    values: [
      context.account_id,
      request.leased_job.job_id,
      request.leased_job.input_frontier,
      graphCommitId,
      graphSequence,
      JSON.stringify(request.staged_result.normalized_result),
    ],
  });
};
