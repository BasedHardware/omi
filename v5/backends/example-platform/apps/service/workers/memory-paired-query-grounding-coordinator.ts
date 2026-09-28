import { isProxy } from "node:util/types";

import type { DurableMemoryWorkErrorCode } from "../../../core/consolidate/state-machine";
import {
  assertMintedMemoryStrategyAssignment,
  type MemoryStrategyAssignmentBundle,
  type MemoryStrategyAssignmentEntry,
} from "../../../core/consolidate/strategy-assignment";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type { MemoryEvaluationEvidenceSourceRequest } from "../stores/memory-evaluation-evidence-source";
import {
  assertMemoryShadowResultRepository,
  assertVerifiedMemoryEvaluationResult,
  pairMemoryEvaluationResults,
  type MemoryEvaluationPair,
  type MemoryEvaluationResult,
  type MemoryEvaluationRole,
  type MemoryShadowResultRepository,
} from "../stores/memory-shadow-result-repository";
import {
  assertMemoryAuthorizedQueryGroundingProducer,
  type AuthorizedQueryGroundingProducerOutcome,
  type AuthorizedQueryGroundingStopCode,
  type MemoryAuthorizedQueryGroundingProducer,
} from "./memory-authorized-query-grounding-producer";

const PORT: unique symbol = Symbol("memory-paired-query-grounding-coordinator");
const CAPABILITY = "memories.experiments.shadow";
const RECEIPT_VERSION = "paired-query-grounding-receipt-v1" as const;
const RUN_ID = /^mer1_[a-f0-9]{64}$/;
const PAIR_ID = /^mep1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const MAX_REPEATS = 20;

export interface PairedQueryGroundingReceipt {
  readonly version: typeof RECEIPT_VERSION;
  readonly pair_ref: string;
  readonly pair_digest: string;
  readonly repeat_ordinal: number;
}

export interface PairedQueryGroundingRequest {
  readonly assignment_bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly evaluation_run_id: string;
  readonly source_request: Readonly<MemoryEvaluationEvidenceSourceRequest>;
  readonly repeats: number;
}

export type PairedQueryGroundingStopCode =
  | AuthorizedQueryGroundingStopCode
  | "dependency_unavailable"
  | "pair_invalid"
  | "pair_storage_retryable"
  | "pair_authorization_or_context"
  | "pair_idempotency_conflict"
  | "pair_storage_unavailable";

interface PairedQueryGroundingCounters {
  readonly observed_model_calls: number;
  readonly staged_results: number;
  readonly replayed_results: number;
  readonly recorded_pairs: number;
  readonly replayed_pairs: number;
}

export type PairedQueryGroundingOutcome =
  | Readonly<PairedQueryGroundingCounters & {
      kind: "completed";
      pair_receipts: readonly Readonly<PairedQueryGroundingReceipt>[];
    }>
  | Readonly<PairedQueryGroundingCounters & {
      kind: "stopped";
      stop_code: PairedQueryGroundingStopCode;
      failure_code: DurableMemoryWorkErrorCode | null;
      pair_receipts: readonly Readonly<PairedQueryGroundingReceipt>[];
    }>;

export interface MemoryPairedQueryGroundingCoordinator {
  readonly [PORT]: true;
  run(
    context: AuthorizedLedgerWriteContext,
    request: PairedQueryGroundingRequest,
  ): Promise<PairedQueryGroundingOutcome>;
}

export interface MemoryPairedQueryGroundingDependencies {
  readonly producer: MemoryAuthorizedQueryGroundingProducer;
  readonly pair_repository: MemoryShadowResultRepository;
}

interface NormalizedRequest {
  readonly bundle: Readonly<MemoryStrategyAssignmentBundle>;
  readonly evaluation_run_id: string;
  readonly source_request: Readonly<MemoryEvaluationEvidenceSourceRequest>;
  readonly repeats: number;
}

const fail = (code: string): never => { throw new TypeError(`memory paired query grounding ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail(code);
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const normalizeRequest = (
  context: AuthorizedLedgerWriteContext,
  value: PairedQueryGroundingRequest,
): Readonly<NormalizedRequest> => {
  const input = exactRecord(value, [
    "assignment_bundle", "evaluation_run_id", "source_request", "repeats",
  ], "invalid_request");
  const bundle = assertMintedMemoryStrategyAssignment(input["assignment_bundle"]);
  if (bundle.owner_account_id !== context.account_id) fail("owner_mismatch");
  if (bundle.work_kind !== "retrieval" && bundle.work_kind !== "composition") fail("not_read_strategy");
  if (bundle.shadows.length === 0) fail("no_selected_shadow");
  const runId = token(input["evaluation_run_id"], "invalid_request");
  if (!RUN_ID.test(runId)) fail("invalid_request");
  const repeats = input["repeats"];
  if (!Number.isSafeInteger(repeats) || (repeats as number) < 1 || (repeats as number) > MAX_REPEATS) {
    fail("invalid_repeats");
  }
  const source = exactRecord(input["source_request"], [
    "source_kind", "source_ref", "input_frontier",
  ], "invalid_source_request");
  if (source["source_kind"] !== "authorized_graph_snapshot") fail("invalid_source_request");
  return Object.freeze({
    bundle,
    evaluation_run_id: runId,
    source_request: Object.freeze({
      source_kind: "authorized_graph_snapshot" as const,
      source_ref: token(source["source_ref"], "invalid_source_request"),
      input_frontier: token(source["input_frontier"], "invalid_source_request"),
    }),
    repeats: repeats as number,
  });
};

const receiptFor = (pair: Readonly<MemoryEvaluationPair>): Readonly<PairedQueryGroundingReceipt> => {
  if (!PAIR_ID.test(pair.pair_id) || !DIGEST.test(pair.pair_digest)
    || !Number.isSafeInteger(pair.repeat_ordinal) || pair.repeat_ordinal < 0) fail("pair_invalid");
  return Object.freeze({
    version: RECEIPT_VERSION,
    pair_ref: pair.pair_id,
    pair_digest: pair.pair_digest,
    repeat_ordinal: pair.repeat_ordinal,
  });
};

const pairStop = (kind: string): PairedQueryGroundingStopCode => {
  if (kind === "serialization_retryable") return "pair_storage_retryable";
  if (kind === "stale_context" || kind === "authorization_denied") return "pair_authorization_or_context";
  if (kind === "idempotency_conflict") return "pair_idempotency_conflict";
  return "pair_storage_unavailable";
};

export const defineMemoryPairedQueryGroundingCoordinator = (
  dependenciesValue: MemoryPairedQueryGroundingDependencies,
): MemoryPairedQueryGroundingCoordinator => {
  const dependencies = exactRecord(dependenciesValue, ["producer", "pair_repository"], "invalid_dependencies");
  const producer = assertMemoryAuthorizedQueryGroundingProducer(dependencies["producer"]);
  const pairRepository = assertMemoryShadowResultRepository(dependencies["pair_repository"]);

  return Object.freeze({
    [PORT]: true as const,
    async run(contextValue, requestValue) {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      if (context.capability !== CAPABILITY) fail("capability_denied");
      const request = normalizeRequest(context, requestValue);
      const receipts: Readonly<PairedQueryGroundingReceipt>[] = [];
      let observedModelCalls = 0;
      let stagedResults = 0;
      let replayedResults = 0;
      let recordedPairs = 0;
      let replayedPairs = 0;

      const counters = (): PairedQueryGroundingCounters => ({
        observed_model_calls: observedModelCalls,
        staged_results: stagedResults,
        replayed_results: replayedResults,
        recorded_pairs: recordedPairs,
        replayed_pairs: replayedPairs,
      });
      const stopped = (
        stopCode: PairedQueryGroundingStopCode,
        failureCode: DurableMemoryWorkErrorCode | null = null,
      ): PairedQueryGroundingOutcome => Object.freeze({
        kind: "stopped" as const,
        stop_code: stopCode,
        failure_code: failureCode,
        pair_receipts: Object.freeze([...receipts]),
        ...counters(),
      });

      const runOne = async (
        assignment: Readonly<MemoryStrategyAssignmentEntry>,
        role: MemoryEvaluationRole,
        repeatOrdinal: number,
      ): Promise<Readonly<MemoryEvaluationResult> | PairedQueryGroundingOutcome> => {
        let outcome: AuthorizedQueryGroundingProducerOutcome;
        try {
          outcome = await producer.run(context, Object.freeze({
            assignment_bundle: request.bundle,
            assignment_id: assignment.assignment_id,
            evaluation_role: role,
            evaluation_run_id: request.evaluation_run_id,
            repeat_ordinal: repeatOrdinal,
            source_request: request.source_request,
          }));
        } catch {
          return stopped("dependency_unavailable", "dependency_unavailable");
        }
        observedModelCalls += outcome.model_calls;
        if (outcome.kind === "stopped") return stopped(outcome.stop_code, outcome.failure_code);
        if (outcome.completion === "staged") stagedResults += 1;
        else replayedResults += 1;
        try { return assertVerifiedMemoryEvaluationResult(outcome.result); }
        catch { return stopped("pair_invalid"); }
      };

      for (let repeatOrdinal = 0; repeatOrdinal < request.repeats; repeatOrdinal += 1) {
        const baseline = await runOne(request.bundle.authority, "baseline", repeatOrdinal);
        if ("kind" in baseline) return baseline;
        for (const shadow of request.bundle.shadows) {
          const candidate = await runOne(shadow, "candidate", repeatOrdinal);
          if ("kind" in candidate) return candidate;
          let pair: Readonly<MemoryEvaluationPair>;
          try { pair = pairMemoryEvaluationResults(baseline, candidate); }
          catch { return stopped("pair_invalid"); }
          let recorded;
          try { recorded = await pairRepository.recordPair(context, pair); }
          catch { return stopped("pair_storage_unavailable"); }
          if (recorded.kind !== "recorded" && recorded.kind !== "replayed") {
            return stopped(pairStop(recorded.kind));
          }
          if (recorded.kind === "recorded") recordedPairs += 1;
          else replayedPairs += 1;
          try { receipts.push(receiptFor(recorded.pair)); }
          catch { return stopped("pair_invalid"); }
        }
      }
      return Object.freeze({
        kind: "completed" as const,
        pair_receipts: Object.freeze([...receipts]),
        ...counters(),
      });
    },
  });
};

export const PAIRED_QUERY_GROUNDING_RECEIPT_VERSION = RECEIPT_VERSION;
