import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertVerifiedMemoryEvaluationPair,
  type MemoryEvaluationPair,
} from "../stores/memory-shadow-result-repository";

const EXPORT_VERSION = "memory-evaluation-export-v1" as const;
const MAX_PAIRS = 10_000;

export interface MemoryEvaluationExportPair {
  readonly ordinal: number;
  readonly pair_ref: string;
  readonly repeat_ordinal: number;
  readonly baseline_result_ref: string;
  readonly baseline_strategy_ref: string;
  readonly candidate_result_ref: string;
  readonly candidate_strategy_ref: string;
}

export interface MemoryEvaluationExportManifest {
  readonly version: typeof EXPORT_VERSION;
  readonly evaluation_mode: "live_shadow" | "offline_replay";
  readonly evaluation_run_ref: string;
  readonly assignment_bundle_ref: string;
  readonly input_ref: string;
  readonly pair_count: number;
  readonly repeat_count: number;
  readonly candidate_strategy_count: number;
  readonly pairs: readonly Readonly<MemoryEvaluationExportPair>[];
  readonly export_digest: string;
}

const fail = (code: string): never => { throw new TypeError(`memory evaluation export ${code}`); };
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const exactPairArray = (value: unknown): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length < 1 || value.length > MAX_PAIRS) fail("invalid_pairs");
  const pairs = value as unknown[];
  const keys = Reflect.ownKeys(pairs);
  if (keys.length !== pairs.length + 1
    || (keys as string[]).some((key) => key !== "length"
      && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= pairs.length))) fail("invalid_pairs");
  const descriptors = Object.getOwnPropertyDescriptors(pairs);
  for (let index = 0; index < pairs.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !("value" in descriptor)) fail("invalid_pairs");
  }
  return pairs;
};

const strategyRef = (
  pair: Readonly<MemoryEvaluationPair>,
  role: "baseline" | "candidate",
  strategyId: string,
): string => `mes1_${sha256CanonicalContent({
  contract_version: "memory-evaluation-export-strategy-ref-v1",
  owner_account_id: pair.owner_account_id,
  account_epoch: pair.account_epoch,
  assignment_bundle_id: pair.assignment_bundle_id,
  evaluation_role: role,
  strategy_id: strategyId,
})}`;

export const buildMemoryEvaluationExport = (
  contextValue: AuthorizedLedgerWriteContext,
  pairValues: readonly MemoryEvaluationPair[],
): Readonly<MemoryEvaluationExportManifest> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== "memories.experiments.shadow") fail("capability_denied");
  const pairs = exactPairArray(pairValues).map(assertVerifiedMemoryEvaluationPair);
  const first = pairs[0]!;
  if (first.owner_account_id !== context.account_id || first.account_epoch !== context.account_epoch) {
    fail("authority_mismatch");
  }
  for (const pair of pairs) {
    if (pair.owner_account_id !== first.owner_account_id
      || pair.account_epoch !== first.account_epoch
      || pair.assignment_bundle_id !== first.assignment_bundle_id
      || pair.evaluation_mode !== first.evaluation_mode
      || pair.evaluation_run_id !== first.evaluation_run_id
      || pair.input_frontier_digest !== first.input_frontier_digest
      || pair.input_digest !== first.input_digest) fail("mixed_export_coordinates");
  }
  const byId = new Map(pairs.map((pair) => [pair.pair_id, pair]));
  if (byId.size !== pairs.length) fail("duplicate_pair");
  const ordered = [...pairs].sort((left, right) => left.repeat_ordinal - right.repeat_ordinal
    || compare(left.candidate_strategy_id, right.candidate_strategy_id)
    || compare(left.pair_id, right.pair_id));
  const rows = Object.freeze(ordered.map((pair, ordinal) => Object.freeze({
    ordinal,
    pair_ref: pair.pair_id,
    repeat_ordinal: pair.repeat_ordinal,
    baseline_result_ref: pair.baseline_result_id,
    baseline_strategy_ref: strategyRef(pair, "baseline", pair.baseline_strategy_id),
    candidate_result_ref: pair.candidate_result_id,
    candidate_strategy_ref: strategyRef(pair, "candidate", pair.candidate_strategy_id),
  })));
  const pairCoordinates = new Set(rows.map((row) => `${row.repeat_ordinal}:${row.candidate_strategy_ref}`));
  if (pairCoordinates.size !== rows.length) fail("duplicate_pair_coordinate");
  const core = Object.freeze({
    version: EXPORT_VERSION,
    evaluation_mode: first.evaluation_mode,
    evaluation_run_ref: first.evaluation_run_id,
    assignment_bundle_ref: `mea1_${sha256CanonicalContent({
      contract_version: "memory-evaluation-export-assignment-ref-v1",
      owner_account_id: first.owner_account_id,
      account_epoch: first.account_epoch,
      assignment_bundle_id: first.assignment_bundle_id,
    })}`,
    input_ref: `mei1_${sha256CanonicalContent({
      contract_version: "memory-evaluation-export-input-ref-v1",
      owner_account_id: first.owner_account_id,
      account_epoch: first.account_epoch,
      input_frontier_digest: first.input_frontier_digest,
      input_digest: first.input_digest,
    })}`,
    pair_count: rows.length,
    repeat_count: new Set(rows.map((row) => row.repeat_ordinal)).size,
    candidate_strategy_count: new Set(rows.map((row) => row.candidate_strategy_ref)).size,
    pairs: rows,
  });
  return Object.freeze({
    ...core,
    export_digest: sha256CanonicalContent(core),
  });
};

export const MEMORY_EVALUATION_EXPORT_VERSION = EXPORT_VERSION;
