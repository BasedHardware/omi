import type { AgentStore } from "./types.js";
import type { ToolInvocationStatus } from "./tool-invocation-ledger.js";

/** A model-facing projection, never a second operation store or execution authority. */
export interface ConversationOperationReceipt {
  invocationId: string;
  runId: string;
  toolName: string;
  status: ToolInvocationStatus;
  retryPolicy: "safe_retry" | "never_auto_retry";
  updatedAtMs: number;
}

const MAX_RECEIPTS = 12;

/**
 * Reconstruct action outcomes from the existing invocation ledger. The run's
 * admitted conversation, rather than its potentially shared session alias,
 * selects the history. Clearing a conversation also clears this derived view.
 * Tool inputs, outputs, filesystem paths and provider errors never enter it.
 */
export function conversationOperationReceipts(
  store: AgentStore,
  input: { ownerId: string; conversationId: string },
): ConversationOperationReceipt[] {
  const owned = store.getOptionalRow(
    "SELECT 1 FROM surface_conversations WHERE owner_id = ? AND conversation_id = ? LIMIT 1",
    [input.ownerId, input.conversationId],
  );
  if (!owned) throw new Error("Operation context requires an owned conversation");
  return store.allRows(
    `SELECT ledger.invocation_id, ledger.run_id, ledger.tool_name, ledger.status,
            ledger.retry_policy, ledger.updated_at_ms
     FROM tool_invocation_ledger AS ledger
     JOIN runs ON runs.run_id = ledger.run_id
     JOIN sessions ON sessions.session_id = runs.session_id
     LEFT JOIN conversation_journal_state AS journal ON journal.conversation_id = ?
     WHERE ledger.owner_id = ? AND sessions.owner_id = ?
       AND json_extract(runs.input_json, '$.admittedContextSnapshot.conversationId') = ?
       AND ledger.effect_class != 'read_only'
       AND (
         json_extract(runs.input_json, '$.admittedContextSnapshot.conversationGeneration') = COALESCE(journal.generation, 1)
         OR (
           json_extract(runs.input_json, '$.admittedContextSnapshot.conversationGeneration') IS NULL
           AND (journal.cleared_at_ms IS NULL OR ledger.prepared_at_ms > journal.cleared_at_ms)
         )
       )
     ORDER BY ledger.updated_at_ms DESC, ledger.invocation_id ASC
     LIMIT ?`,
    [input.conversationId, input.ownerId, input.ownerId, input.conversationId, MAX_RECEIPTS],
  ).map((row) => ({
    invocationId: String(row.invocation_id),
    runId: String(row.run_id),
    toolName: String(row.tool_name),
    status: String(row.status) as ToolInvocationStatus,
    retryPolicy: String(row.retry_policy) as ConversationOperationReceipt["retryPolicy"],
    updatedAtMs: Number(row.updated_at_ms),
  }));
}
