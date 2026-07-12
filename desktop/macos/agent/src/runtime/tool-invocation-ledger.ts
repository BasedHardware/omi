import { createHash } from "node:crypto";

import { stableJsonStringify } from "./kernel-support.js";
import type { AgentStore } from "./types.js";

export type ToolInvocationEffectClass = "read_only" | "idempotent_write" | "non_idempotent_write";
export type ToolInvocationRetryPolicy = "safe_retry" | "never_auto_retry";
export type ToolInvocationStatus = "prepared" | "dispatched" | "succeeded" | "failed" | "outcome_unknown";

export interface ToolInvocationIdentity {
  invocationId: string;
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  profileGeneration: number;
  manifestVersion: number;
  manifestDigest: string;
  daemonBootEpoch: string;
  executionGeneration: number;
  inputHash: string;
}

export interface ToolInvocationLedgerRecord extends ToolInvocationIdentity {
  toolName: string;
  effectClass: ToolInvocationEffectClass;
  retryPolicy: ToolInvocationRetryPolicy;
  status: ToolInvocationStatus;
  resultHash: string | null;
  errorCode: string | null;
  preparedAtMs: number;
  dispatchedAtMs: number | null;
  completedAtMs: number | null;
  updatedAtMs: number;
}

/**
 * Bounded, non-content execution evidence suitable for control-plane inspection.
 * Inputs, results, and their hashes deliberately stay out of this projection.
 */
export interface ToolInvocationSummary {
  invocationId: string;
  runId: string;
  attemptId: string;
  toolName: string;
  status: ToolInvocationStatus;
  errorCode: string | null;
  preparedAtMs: number;
  dispatchedAtMs: number | null;
  completedAtMs: number | null;
  updatedAtMs: number;
}

export function canonicalInputHash(input: Record<string, unknown>): string {
  return `sha256:${createHash("sha256").update(stableJsonStringify(input)).digest("hex")}`;
}

export function resultHash(result: string): string {
  return `sha256:${createHash("sha256").update(result).digest("hex")}`;
}

export function prepareToolInvocation(
  store: AgentStore,
  input: ToolInvocationIdentity & {
    toolName: string;
    effectClass: ToolInvocationEffectClass;
    retryPolicy: ToolInvocationRetryPolicy;
    nowMs: number;
  },
): ToolInvocationLedgerRecord {
  try {
    store.execute(
      `INSERT INTO tool_invocation_ledger(
        invocation_id, owner_id, session_id, run_id, attempt_id,
        profile_generation, manifest_version, manifest_digest, daemon_boot_epoch, execution_generation,
        tool_name, input_hash, effect_class, retry_policy, status,
        prepared_at_ms, updated_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?, ?)`,
      [
        input.invocationId,
        input.ownerId,
        input.sessionId,
        input.runId,
        input.attemptId,
        input.profileGeneration,
        input.manifestVersion,
        input.manifestDigest,
        input.daemonBootEpoch,
        input.executionGeneration,
        input.toolName,
        input.inputHash,
        input.effectClass,
        input.retryPolicy,
        input.nowMs,
        input.nowMs,
      ],
    );
  } catch (error) {
    if (error instanceof Error && error.message.includes("UNIQUE constraint failed")) {
      throw new Error("Tool invocation id has already been prepared");
    }
    throw error;
  }
  return readToolInvocation(store, input.invocationId);
}

export function markToolInvocationDispatched(
  store: AgentStore,
  identity: ToolInvocationIdentity,
  nowMs: number,
): ToolInvocationLedgerRecord {
  const changed = store.execute(
    `UPDATE tool_invocation_ledger
     SET status = 'dispatched', dispatched_at_ms = ?, updated_at_ms = ?
     WHERE invocation_id = ? AND owner_id = ? AND session_id = ? AND run_id = ? AND attempt_id = ?
       AND profile_generation = ? AND manifest_version = ? AND manifest_digest = ? AND daemon_boot_epoch = ?
       AND execution_generation = ? AND input_hash = ? AND status = 'prepared'`,
    [
      nowMs,
      nowMs,
      identity.invocationId,
      identity.ownerId,
      identity.sessionId,
      identity.runId,
      identity.attemptId,
      identity.profileGeneration,
      identity.manifestVersion,
      identity.manifestDigest,
      identity.daemonBootEpoch,
      identity.executionGeneration,
      identity.inputHash,
    ],
  );
  if (changed !== 1) throw new Error("Prepared tool invocation tuple is stale or already dispatched");
  return readToolInvocation(store, identity.invocationId);
}

export function completeToolInvocation(
  store: AgentStore,
  input: ToolInvocationIdentity & { outcome: "succeeded" | "failed"; result: string; nowMs: number },
): ToolInvocationLedgerRecord {
  const changed = store.execute(
    `UPDATE tool_invocation_ledger
     SET status = ?, result_hash = ?, completed_at_ms = ?, updated_at_ms = ?
     WHERE invocation_id = ? AND owner_id = ? AND session_id = ? AND run_id = ? AND attempt_id = ?
       AND profile_generation = ? AND manifest_version = ? AND manifest_digest = ? AND daemon_boot_epoch = ?
       AND execution_generation = ? AND input_hash = ? AND status = 'dispatched'`,
    [
      input.outcome,
      resultHash(input.result),
      input.nowMs,
      input.nowMs,
      input.invocationId,
      input.ownerId,
      input.sessionId,
      input.runId,
      input.attemptId,
      input.profileGeneration,
      input.manifestVersion,
      input.manifestDigest,
      input.daemonBootEpoch,
      input.executionGeneration,
      input.inputHash,
    ],
  );
  if (changed !== 1) throw new Error("Tool execution result tuple is stale, duplicated, or was never dispatched");
  return readToolInvocation(store, input.invocationId);
}

export function markToolInvocationOutcomeUnknown(
  store: AgentStore,
  identity: ToolInvocationIdentity,
  errorCode: string,
  nowMs: number,
): ToolInvocationLedgerRecord {
  if (!/^[A-Za-z0-9_.:-]{1,128}$/.test(errorCode)) throw new Error("Tool invocation error code is unbounded");
  const changed = store.execute(
    `UPDATE tool_invocation_ledger
     SET status = 'outcome_unknown', error_code = ?, completed_at_ms = ?, updated_at_ms = ?
     WHERE invocation_id = ? AND owner_id = ? AND session_id = ? AND run_id = ? AND attempt_id = ?
       AND profile_generation = ? AND manifest_version = ? AND manifest_digest = ? AND daemon_boot_epoch = ?
       AND execution_generation = ? AND input_hash = ? AND status = 'dispatched'`,
    [
      errorCode,
      nowMs,
      nowMs,
      identity.invocationId,
      identity.ownerId,
      identity.sessionId,
      identity.runId,
      identity.attemptId,
      identity.profileGeneration,
      identity.manifestVersion,
      identity.manifestDigest,
      identity.daemonBootEpoch,
      identity.executionGeneration,
      identity.inputHash,
    ],
  );
  if (changed !== 1) throw new Error("Tool invocation cannot transition to outcome_unknown");
  return readToolInvocation(store, identity.invocationId);
}

export function readToolInvocation(store: AgentStore, invocationId: string): ToolInvocationLedgerRecord {
  return toolInvocationFromRow(store.getRow(
    "SELECT * FROM tool_invocation_ledger WHERE invocation_id = ?",
    [invocationId],
  ));
}

export function listRunToolInvocationSummaries(
  store: AgentStore,
  runId: string,
  limit = 100,
): ToolInvocationSummary[] {
  const boundedLimit = Number.isSafeInteger(limit) ? Math.min(Math.max(limit, 1), 500) : 100;
  return store.allRows(
    `SELECT invocation_id, run_id, attempt_id, tool_name, status, error_code,
            prepared_at_ms, dispatched_at_ms, completed_at_ms, updated_at_ms
     FROM tool_invocation_ledger
     WHERE run_id = ?
     ORDER BY prepared_at_ms ASC, invocation_id ASC
     LIMIT ?`,
    [runId, boundedLimit],
  ).map((row) => ({
    invocationId: String(row.invocation_id),
    runId: String(row.run_id),
    attemptId: String(row.attempt_id),
    toolName: String(row.tool_name),
    status: String(row.status) as ToolInvocationStatus,
    errorCode: row.error_code == null ? null : String(row.error_code),
    preparedAtMs: Number(row.prepared_at_ms),
    dispatchedAtMs: row.dispatched_at_ms == null ? null : Number(row.dispatched_at_ms),
    completedAtMs: row.completed_at_ms == null ? null : Number(row.completed_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
  }));
}

export function toolInvocationObservability(store: AgentStore): Record<ToolInvocationStatus, number> {
  const counts: Record<ToolInvocationStatus, number> = {
    prepared: 0,
    dispatched: 0,
    succeeded: 0,
    failed: 0,
    outcome_unknown: 0,
  };
  for (const row of store.allRows("SELECT status, COUNT(*) AS count FROM tool_invocation_ledger GROUP BY status")) {
    counts[String(row.status) as ToolInvocationStatus] = Number(row.count);
  }
  return counts;
}

function toolInvocationFromRow(row: Record<string, unknown>): ToolInvocationLedgerRecord {
  return {
    invocationId: String(row.invocation_id),
    ownerId: String(row.owner_id),
    sessionId: String(row.session_id),
    runId: String(row.run_id),
    attemptId: String(row.attempt_id),
    profileGeneration: Number(row.profile_generation),
    manifestVersion: Number(row.manifest_version),
    manifestDigest: String(row.manifest_digest),
    daemonBootEpoch: String(row.daemon_boot_epoch),
    executionGeneration: Number(row.execution_generation),
    toolName: String(row.tool_name),
    inputHash: String(row.input_hash),
    effectClass: String(row.effect_class) as ToolInvocationEffectClass,
    retryPolicy: String(row.retry_policy) as ToolInvocationRetryPolicy,
    status: String(row.status) as ToolInvocationStatus,
    resultHash: row.result_hash == null ? null : String(row.result_hash),
    errorCode: row.error_code == null ? null : String(row.error_code),
    preparedAtMs: Number(row.prepared_at_ms),
    dispatchedAtMs: row.dispatched_at_ms == null ? null : Number(row.dispatched_at_ms),
    completedAtMs: row.completed_at_ms == null ? null : Number(row.completed_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
  };
}
