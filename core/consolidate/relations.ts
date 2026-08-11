import { isProxy } from "node:util/types";
import { sha256CanonicalRedacted, type CanonicalJson } from "../ledger";
import { compareStrings } from "../order";
import type { Predicate, PredicateAssertion } from "../schema";
import { normalizePredicateName, predicateIdForName, predicateRevisionForObservation } from "./predicate-identity";

export interface PredicateAlignmentPort {
  invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown>;
}

export interface PredicateAlignmentProposal {
  assertions: readonly {
    predicate_id: string;
    target_predicate_id: string;
    slot_aliases?: readonly { from_slot_id: string; to_slot_id: string }[];
  }[];
}

/**
 * `slot_ids` is retained at the model-port boundary for compatibility. For a
 * name-v2 predicate it contains semantic roles from `observed_roles`, never
 * legacy window-local slot ordinals.
 */
export interface PredicateAlignmentRequest {
  predicate_frontier: string;
  predicates: readonly { predicate_id: string; name: string; slot_ids: readonly string[] }[];
}

/** Every field that can change the meaning of one adjudication is explicit. */
export interface PredicateAlignmentAdjudicationContract {
  model_version: string;
  strategy: string;
  prompt_version: string;
  schema_version: string;
  code_version: string;
}

export interface PredicateAlignmentOptions {
  /** The owner whose vocabulary may enter this model question. */
  owner_account_id: string;
  /** Positive, finite upper bound on the exact prompt-shaped cost of a call. */
  batch_prompt_budget: number;
  /** Positive bounded number of model calls in flight. */
  model_concurrency: number;
  /** Positive hard bound on questions emitted by one resumable invocation. */
  max_questions_per_invocation: number;
  /**
   * Adapter-owned exact cost of the prompt produced for this request. The core
   * cannot silently approximate a provider prompt from storage JSON.
   */
  prompt_cost: (request: PredicateAlignmentRequest) => number;
  adjudication_contract: PredicateAlignmentAdjudicationContract;
  /**
   * Exact prior successes used to reconstruct pair coverage incrementally.
   * The adapter may supply one only after the corresponding graph result is
   * durable; a model response or settlement digest alone is not authority.
   */
  successful_questions?: readonly PredicateAlignmentSuccessfulQuestion[];
}

export interface PredicateAlignmentSuccessfulQuestion {
  batch_question_digest: string;
  predicate_frontier: string;
  predicate_ids: readonly string[];
  response_digest: string;
  result_digest: string;
}

export type PredicateProposalRejectionCode =
  | "invalid_proposal"
  | "invented_predicate"
  | "self_alias"
  | "predicate_outside_successful_batch"
  | "ambiguous_predicate_owner"
  | "cross_owner_alias"
  | "invalid_slot_alias";

export interface PredicateProposalRejection {
  proposal_index: number;
  code: PredicateProposalRejectionCode;
}

export type PredicateAlignmentRetryableErrorCode =
  | "batch_prompt_budget_exceeded"
  | "model_invoke_failed"
  | "model_response_invalid";

interface PredicateAlignmentBatchCoordinate {
  /** Position in the deterministic complete batch plan, including settled skips. */
  batch_index: number;
  /** Contract + exact ordered model question; safe to persist as an opaque coordinate. */
  batch_question_digest: string;
  /** Canonical owner + exact-batch vocabulary frontier. */
  predicate_frontier: string;
  predicate_ids: readonly string[];
}

export interface PredicateAlignmentBatchSuccess extends PredicateAlignmentBatchCoordinate {
  kind: "success";
  /** Present only on success: persistence may mark this exact question settled. */
  settleable_batch_digest: string;
  response_digest: string;
  result_digest: string;
  assertions: readonly PredicateAssertion[];
  rejected_proposals: readonly PredicateProposalRejection[];
}

export interface PredicateAlignmentBatchRetryableError extends PredicateAlignmentBatchCoordinate {
  kind: "retryable_error";
  error_code: PredicateAlignmentRetryableErrorCode;
}

export type PredicateAlignmentBatchOutcome = PredicateAlignmentBatchSuccess | PredicateAlignmentBatchRetryableError;

export type PredicateExclusionCode = "owner_mismatch" | "legacy_identity_version" | "invalid_name_v2_revision";
export interface PredicateAlignmentExclusion {
  predicate_revision_id: string;
  code: PredicateExclusionCode;
}

export interface PredicateAlignmentResult {
  assertions: readonly PredicateAssertion[];
  batch_outcomes: readonly PredicateAlignmentBatchOutcome[];
  skipped_settled_batch_digests: readonly string[];
  excluded_predicates: readonly PredicateAlignmentExclusion[];
  coverage: PredicateAlignmentCoverage;
}

export interface PredicateAlignmentCoverage {
  eligible_predicates: number;
  total_pairs: number;
  valid_successful_questions: number;
  covered_pairs_before_plan: number;
  remaining_pairs_before_plan: number;
  planned_questions: number;
  planned_newly_covered_pairs: number;
  remaining_pairs_after_plan: number;
  maximum_remaining_questions_after_plan: number;
}

type PredicateView = {
  predicate_id: string;
  name: string;
  slot_ids: readonly string[];
};

type OwnerKnowledge = { owners: ReadonlySet<string>; roles: ReadonlySet<string> };

const MAX_ALIGNMENT_CONCURRENCY = 64;
const MAX_ALIGNMENT_QUESTIONS_PER_INVOCATION = 4_096;
const MAX_ALIGNMENT_PROMPT_BUDGET = 10_000_000;
const MAX_PROPOSALS_PER_BATCH = 4_096;
const MAX_MODEL_IDENTIFIER_LENGTH = 1_024;

const requireNonEmpty = (value: string, code: string): void => {
  if (!value.trim()) throw new TypeError(code);
};

const validateOptions = (options: PredicateAlignmentOptions): void => {
  if (!Number.isSafeInteger(options.batch_prompt_budget)
    || options.batch_prompt_budget < 1
    || options.batch_prompt_budget > MAX_ALIGNMENT_PROMPT_BUDGET) {
    throw new RangeError("predicate_alignment_prompt_budget_invalid");
  }
  if (!Number.isSafeInteger(options.model_concurrency)
    || options.model_concurrency < 1
    || options.model_concurrency > MAX_ALIGNMENT_CONCURRENCY) {
    throw new RangeError("predicate_alignment_concurrency_invalid");
  }
  if (!Number.isSafeInteger(options.max_questions_per_invocation)
    || options.max_questions_per_invocation < 1
    || options.max_questions_per_invocation > MAX_ALIGNMENT_QUESTIONS_PER_INVOCATION) {
    throw new RangeError("predicate_alignment_question_limit_invalid");
  }
  if (typeof options.prompt_cost !== "function") throw new TypeError("predicate_alignment_prompt_cost_missing");
  requireNonEmpty(options.owner_account_id, "predicate_alignment_owner_invalid");
  const contract = options.adjudication_contract;
  if (!contract || typeof contract !== "object") throw new TypeError("predicate_alignment_contract_missing");
  requireNonEmpty(contract.model_version, "predicate_alignment_model_version_invalid");
  requireNonEmpty(contract.strategy, "predicate_alignment_strategy_invalid");
  requireNonEmpty(contract.prompt_version, "predicate_alignment_prompt_version_invalid");
  requireNonEmpty(contract.schema_version, "predicate_alignment_schema_version_invalid");
  requireNonEmpty(contract.code_version, "predicate_alignment_code_version_invalid");
};

const measuredCost = (options: PredicateAlignmentOptions, request: PredicateAlignmentRequest): number => {
  const cost = options.prompt_cost(request);
  if (!Number.isSafeInteger(cost) || cost < 1) throw new RangeError("predicate_alignment_prompt_cost_invalid");
  return cost;
};

export const predicateAlignmentBatchDigest = (
  contract: PredicateAlignmentAdjudicationContract,
  request: PredicateAlignmentRequest,
): string => {
  const seed: CanonicalJson = {
    kind: "predicate-alignment-batch-v2",
    adjudication_contract: {
      model_version: contract.model_version,
      strategy: contract.strategy,
      prompt_version: contract.prompt_version,
      schema_version: contract.schema_version,
      code_version: contract.code_version,
    },
    question: {
      predicate_frontier: request.predicate_frontier,
      predicates: request.predicates.map((predicate) => ({
        predicate_id: predicate.predicate_id,
        name: predicate.name,
        slot_ids: predicate.slot_ids,
      })),
    },
  };
  return sha256CanonicalRedacted(seed);
};

const mapLimit = async <T, R>(
  items: readonly T[],
  limit: number,
  task: (item: T, index: number) => Promise<R>,
): Promise<R[]> => {
  const results = new Array<R>(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await task(items[index]!, index);
    }
  }));
  return results;
};

const isPlainRecord = (value: unknown): value is Record<string, unknown> => {
  if (value === null || typeof value !== "object" || isProxy(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype;
};

const ownData = (record: Record<string, unknown>, key: string): unknown => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && "value" in descriptor ? descriptor.value : undefined;
};

const densePlainArray = (value: unknown, maxLength: number): value is readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype || value.length > maxLength) return false;
  const expectedKeys = new Set(["length", ...Array.from({ length: value.length }, (_, index) => String(index))]);
  if (Reflect.ownKeys(value).some((key) => typeof key !== "string" || !expectedKeys.has(key))) return false;
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor)) return false;
  }
  return true;
};

const responseAssertions = (response: unknown): readonly unknown[] | null => {
  if (!isPlainRecord(response)) return null;
  const keys = Reflect.ownKeys(response);
  if (keys.length !== 1 || keys[0] !== "assertions") return null;
  const assertions = ownData(response, "assertions");
  return densePlainArray(assertions, MAX_PROPOSALS_PER_BATCH) ? assertions : null;
};

const isPlainJson = (value: unknown, stack = new WeakSet<object>()): value is CanonicalJson => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || isProxy(value) || stack.has(value)) return false;
  stack.add(value);
  try {
    if (Array.isArray(value)) {
      if (Object.getPrototypeOf(value) !== Array.prototype) return false;
      const expectedKeys = new Set(["length", ...Array.from({ length: value.length }, (_, index) => String(index))]);
      if (Reflect.ownKeys(value).some((key) => typeof key !== "string" || !expectedKeys.has(key))) return false;
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
        if (!descriptor || !("value" in descriptor) || !isPlainJson(descriptor.value, stack)) return false;
      }
      return true;
    }
    if (Object.getPrototypeOf(value) !== Object.prototype) return false;
    if (Reflect.ownKeys(value).some((key) => typeof key !== "string")) return false;
    for (const key of Object.keys(value)) {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (!descriptor || !("value" in descriptor) || !isPlainJson(descriptor.value, stack)) return false;
    }
    return true;
  } finally {
    stack.delete(value);
  }
};

const readString = (record: Record<string, unknown>, key: string): string | null => {
  const value = ownData(record, key);
  return typeof value === "string" && value.length > 0 && value.length <= MAX_MODEL_IDENTIFIER_LENGTH ? value : null;
};

const parseSlotAliases = (
  value: unknown,
  sourceRoles: ReadonlySet<string>,
  targetRoles: ReadonlySet<string>,
): { from_slot_id: string; to_slot_id: string }[] | null => {
  if (value === undefined) return [];
  if (!densePlainArray(value, 256)) return null;
  const aliases = new Map<string, { from_slot_id: string; to_slot_id: string }>();
  for (const raw of value) {
    if (!isPlainRecord(raw)) return null;
    const keys = Reflect.ownKeys(raw);
    if (keys.length !== 2 || !keys.includes("from_slot_id") || !keys.includes("to_slot_id")) return null;
    const from_slot_id = readString(raw, "from_slot_id");
    const to_slot_id = readString(raw, "to_slot_id");
    if (!from_slot_id || !to_slot_id || !sourceRoles.has(from_slot_id) || !targetRoles.has(to_slot_id)) return null;
    aliases.set(`${from_slot_id}\u0000${to_slot_id}`, { from_slot_id, to_slot_id });
  }
  return [...aliases.values()].sort((left, right) =>
    compareStrings(left.from_slot_id, right.from_slot_id) || compareStrings(left.to_slot_id, right.to_slot_id));
};

const buildView = (predicates: readonly Predicate[], ownerAccountId: string): {
  view: readonly PredicateView[];
  knowledge: ReadonlyMap<string, OwnerKnowledge>;
  excluded: readonly PredicateAlignmentExclusion[];
} => {
  const merged = new Map<string, { name: string; owners: Set<string>; roles: Set<string> }>();
  const excluded: PredicateAlignmentExclusion[] = [];
  for (const predicate of predicates) {
    if (predicate.owner_account_id !== ownerAccountId) {
      excluded.push({ predicate_revision_id: predicate.predicate_revision_id, code: "owner_mismatch" });
      continue;
    }
    if (predicate.identity_version !== "name-v2") {
      excluded.push({ predicate_revision_id: predicate.predicate_revision_id, code: "legacy_identity_version" });
      continue;
    }
    if (!Array.isArray(predicate.observed_roles)) {
      excluded.push({ predicate_revision_id: predicate.predicate_revision_id, code: "invalid_name_v2_revision" });
      continue;
    }
    const name = normalizePredicateName(predicate.identity_name);
    const displayName = normalizePredicateName(predicate.display_name);
    const roles = predicate.observed_roles.map((role) => role.trim()).filter(Boolean);
    if (!name || displayName !== name || predicate.predicate_id !== predicateIdForName(name)
      || roles.length !== predicate.observed_roles.length || new Set(roles).size !== roles.length) {
      excluded.push({ predicate_revision_id: predicate.predicate_revision_id, code: "invalid_name_v2_revision" });
      continue;
    }
    const expectedRevision = predicateRevisionForObservation({
      owner_account_id: predicate.owner_account_id,
      predicate_id: predicate.predicate_id,
      display_name: predicate.display_name,
      roles: predicate.observed_roles,
      lifecycle: predicate.lifecycle,
    });
    if (predicate.predicate_revision_id !== expectedRevision.revision_id
      || predicate.identity_name !== expectedRevision.predicate.identity_name
      || predicate.slot_ids.length !== 0
      || JSON.stringify(predicate.observed_roles) !== JSON.stringify(expectedRevision.predicate.observed_roles)) {
      excluded.push({ predicate_revision_id: predicate.predicate_revision_id, code: "invalid_name_v2_revision" });
      continue;
    }
    const existing = merged.get(predicate.predicate_id);
    if (existing && existing.name !== name) {
      excluded.push({ predicate_revision_id: predicate.predicate_revision_id, code: "invalid_name_v2_revision" });
      continue;
    }
    const entry = existing ?? { name, owners: new Set<string>(), roles: new Set<string>() };
    entry.owners.add(predicate.owner_account_id);
    for (const role of roles) entry.roles.add(role);
    merged.set(predicate.predicate_id, entry);
  }
  const view = [...merged.entries()]
    .map(([predicate_id, entry]) => ({
      predicate_id,
      name: entry.name,
      slot_ids: [...entry.roles].sort(compareStrings),
    }))
    .sort((left, right) => compareStrings(left.name, right.name) || compareStrings(left.predicate_id, right.predicate_id));
  return {
    view,
    knowledge: new Map([...merged.entries()].map(([id, entry]) => [id, { owners: entry.owners, roles: entry.roles }])),
    excluded: excluded.sort((left, right) => compareStrings(left.predicate_revision_id, right.predicate_revision_id)),
  };
};

/**
 * Canonical work frontier for predicate adjudication. It changes when the
 * owner-local name-v2 vocabulary or observed semantic roles change, but not
 * when the alignment transition writes its own assertion. Drivers should use
 * this instead of a graph sequence, which would make every successful batch
 * invalidate and immediately re-ask itself.
 */
const vocabularyFrontierForView = (view: readonly PredicateView[], ownerAccountId: string): string => {
  return sha256CanonicalRedacted({
    kind: "predicate-alignment-vocabulary-frontier-v2",
    owner_account_id: ownerAccountId,
    predicates: view.map((predicate) => ({
      predicate_id: predicate.predicate_id,
      name: predicate.name,
      observed_roles: predicate.slot_ids,
    })),
  });
};

export const predicateAlignmentVocabularyFrontier = (
  predicates: readonly Predicate[],
  ownerAccountId: string,
): string => vocabularyFrontierForView(buildView(predicates, ownerAccountId).view, ownerAccountId);

interface PlannedBatch {
  request: PredicateAlignmentRequest;
  cost: number;
  digest: string;
  batch_index: number;
}

const pairKey = (left: number, right: number): string => left < right ? `${left}:${right}` : `${right}:${left}`;
const digestPattern = /^[0-9a-f]{64}$/;

const validSuccessfulQuestions = (
  view: readonly PredicateView[],
  options: PredicateAlignmentOptions,
): readonly PredicateAlignmentSuccessfulQuestion[] => {
  const byId = new Map(view.map((predicate) => [predicate.predicate_id, predicate]));
  const valid = new Map<string, PredicateAlignmentSuccessfulQuestion>();
  const records = options.successful_questions ?? [];
  if (!densePlainArray(records, 100_000)) return [];
  for (const raw of records) {
    if (!isPlainRecord(raw)) continue;
    const batch_question_digest = ownData(raw, "batch_question_digest");
    const predicate_frontier = ownData(raw, "predicate_frontier");
    const predicate_ids = ownData(raw, "predicate_ids");
    const response_digest = ownData(raw, "response_digest");
    const result_digest = ownData(raw, "result_digest");
    if (typeof batch_question_digest !== "string" || !digestPattern.test(batch_question_digest)
      || typeof predicate_frontier !== "string" || !digestPattern.test(predicate_frontier)
      || typeof response_digest !== "string" || !digestPattern.test(response_digest)
      || typeof result_digest !== "string" || !digestPattern.test(result_digest)
      || !densePlainArray(predicate_ids, 100_000)
      || predicate_ids.some((id) => typeof id !== "string")
      || new Set(predicate_ids).size !== predicate_ids.length) continue;
    const predicates = (predicate_ids as readonly string[]).flatMap((id) => {
      const predicate = byId.get(id);
      return predicate ? [predicate] : [];
    }).sort((left, right) => compareStrings(left.name, right.name)
      || compareStrings(left.predicate_id, right.predicate_id));
    if (predicates.length !== predicate_ids.length
      || predicates.some((predicate, index) => predicate.predicate_id !== predicate_ids[index])) continue;
    const request: PredicateAlignmentRequest = {
      predicate_frontier: vocabularyFrontierForView(predicates, options.owner_account_id),
      predicates,
    };
    if (request.predicate_frontier !== predicate_frontier
      || predicateAlignmentBatchDigest(options.adjudication_contract, request) !== batch_question_digest) continue;
    valid.set(batch_question_digest, {
      batch_question_digest,
      predicate_frontier,
      predicate_ids: [...predicate_ids] as string[],
      response_digest,
      result_digest,
    });
  }
  return [...valid.values()].sort((left, right) => compareStrings(left.batch_question_digest, right.batch_question_digest));
};

const planBatches = (
  view: readonly PredicateView[],
  options: PredicateAlignmentOptions,
): { planned: readonly PlannedBatch[]; coverage: PredicateAlignmentCoverage; valid_successes: readonly PredicateAlignmentSuccessfulQuestion[] } => {
  const requestFor = (predicates: readonly PredicateView[]): PredicateAlignmentRequest => ({
    predicate_frontier: vocabularyFrontierForView(predicates, options.owner_account_id),
    predicates,
  });
  const indexById = new Map(view.map((predicate, index) => [predicate.predicate_id, index]));
  const totalPairs = view.length * (view.length - 1) / 2;
  const validSuccesses = validSuccessfulQuestions(view, options);
  const covered = new Set<string>();
  for (const success of validSuccesses) {
    const indices = success.predicate_ids.map((id) => indexById.get(id)!);
    for (let left = 0; left < indices.length; left += 1) {
      for (let right = left + 1; right < indices.length; right += 1) {
        covered.add(pairKey(indices[left]!, indices[right]!));
      }
    }
  }
  const uncovered = new Set<string>();
  for (let left = 0; left < view.length; left += 1) {
    for (let right = left + 1; right < view.length; right += 1) {
      const key = pairKey(left, right);
      if (!covered.has(key)) uncovered.add(key);
    }
  }
  const before = uncovered.size;
  const requests: PredicateAlignmentRequest[] = [];
  while (uncovered.size && requests.length < options.max_questions_per_invocation) {
    const seed = uncovered.values().next().value as string | undefined;
    if (!seed) break;
    const [seedLeft, seedRight] = seed.split(":").map(Number) as [number, number];
    const block = [seedLeft, seedRight];
    const selected = new Set(block);
    const scores = new Int32Array(view.length);
    for (let candidate = 0; candidate < view.length; candidate += 1) {
      if (selected.has(candidate)) continue;
      scores[candidate] = Number(uncovered.has(pairKey(candidate, seedLeft)))
        + Number(uncovered.has(pairKey(candidate, seedRight)));
    }
    let currentCost = measuredCost(options, requestFor(block.map((index) => view[index]!)));
    while (true) {
      const candidates: { index: number; score: number }[] = [];
      for (let candidate = 0; candidate < view.length; candidate += 1) {
        if (selected.has(candidate)) continue;
        const score = scores[candidate]!;
        if (score > 0) candidates.push({ index: candidate, score });
      }
      candidates.sort((left, right) => right.score - left.score || left.index - right.index);
      let winner = -1;
      let winnerCost = 0;
      for (const candidate of candidates) {
        const indices = [...block, candidate.index].sort((left, right) => left - right);
        const cost = measuredCost(options, requestFor(indices.map((index) => view[index]!)));
        if (cost < currentCost) throw new RangeError("predicate_alignment_prompt_cost_not_monotone");
        if (cost <= options.batch_prompt_budget) {
          winner = candidate.index;
          winnerCost = cost;
          break;
        }
      }
      if (winner < 0) break;
      block.push(winner);
      block.sort((left, right) => left - right);
      selected.add(winner);
      scores[winner] = -1;
      for (let candidate = 0; candidate < view.length; candidate += 1) {
        if (!selected.has(candidate) && uncovered.has(pairKey(candidate, winner))) scores[candidate]! += 1;
      }
      currentCost = winnerCost;
    }
    for (let left = 0; left < block.length; left += 1) {
      for (let right = left + 1; right < block.length; right += 1) {
        uncovered.delete(pairKey(block[left]!, block[right]!));
      }
    }
    requests.push(requestFor(block.map((index) => view[index]!)));
  }
  const planned = requests.map((request, batch_index) => ({
    request,
    cost: measuredCost(options, request),
    digest: predicateAlignmentBatchDigest(options.adjudication_contract, request),
    batch_index,
  }));
  return {
    planned,
    valid_successes: validSuccesses,
    coverage: {
      eligible_predicates: view.length,
      total_pairs: totalPairs,
      valid_successful_questions: validSuccesses.length,
      covered_pairs_before_plan: totalPairs - before,
      remaining_pairs_before_plan: before,
      planned_questions: planned.length,
      planned_newly_covered_pairs: before - uncovered.size,
      remaining_pairs_after_plan: uncovered.size,
      maximum_remaining_questions_after_plan: uncovered.size,
    },
  };
};

const reject = (
  rejected: PredicateProposalRejection[],
  proposal_index: number,
  code: PredicateProposalRejectionCode,
): null => {
  rejected.push({ proposal_index, code });
  return null;
};

const proposalAssertion = (
  raw: unknown,
  proposal_index: number,
  batch: PlannedBatch,
  knowledge: ReadonlyMap<string, OwnerKnowledge>,
  rejected: PredicateProposalRejection[],
): PredicateAssertion | null => {
  if (!isPlainRecord(raw)) return reject(rejected, proposal_index, "invalid_proposal");
  const keys = Reflect.ownKeys(raw);
  if (keys.some((key) => typeof key !== "string")
    || keys.some((key) => !["predicate_id", "target_predicate_id", "slot_aliases"].includes(key as string))
    || !keys.includes("predicate_id")
    || !keys.includes("target_predicate_id")) return reject(rejected, proposal_index, "invalid_proposal");
  const predicate_id = readString(raw, "predicate_id");
  const target_predicate_id = readString(raw, "target_predicate_id");
  if (!predicate_id || !target_predicate_id) return reject(rejected, proposal_index, "invalid_proposal");
  if (predicate_id === target_predicate_id) return reject(rejected, proposal_index, "self_alias");
  const source = knowledge.get(predicate_id);
  const target = knowledge.get(target_predicate_id);
  if (!source || !target) return reject(rejected, proposal_index, "invented_predicate");
  const batchIds = new Set(batch.request.predicates.map((predicate) => predicate.predicate_id));
  if (!batchIds.has(predicate_id) || !batchIds.has(target_predicate_id)) {
    return reject(rejected, proposal_index, "predicate_outside_successful_batch");
  }
  if (source.owners.size !== 1 || target.owners.size !== 1) {
    return reject(rejected, proposal_index, "ambiguous_predicate_owner");
  }
  const sourceOwner = [...source.owners][0]!;
  const targetOwner = [...target.owners][0]!;
  if (sourceOwner !== targetOwner) return reject(rejected, proposal_index, "cross_owner_alias");
  const slot_aliases = parseSlotAliases(ownData(raw, "slot_aliases"), source.roles, target.roles);
  if (slot_aliases === null) return reject(rejected, proposal_index, "invalid_slot_alias");
  return {
    assertion_id: `predicate-alias:${sha256CanonicalRedacted({
      kind: "predicate-alias-assertion-v2",
      owner_account_id: sourceOwner,
      batch_question_digest: batch.digest,
      predicate_id,
      target_predicate_id,
      slot_aliases,
    })}`,
    owner_account_id: sourceOwner,
    predicate_id,
    relation: "alias_of",
    target_predicate_id,
    slot_aliases,
    alias_frontier: batch.request.predicate_frontier,
    admission: "accepted",
    lifecycle: "active",
    supersedes_assertion_id: null,
  };
};

/**
 * Bounded deterministic predicate alignment. Settled work is skipped only by
 * its exact contract-and-question digest; failures remain retryable and never
 * erase successful sibling batches.
 */
export const invokePredicateAlignment = async (
  model: PredicateAlignmentPort,
  predicates: readonly Predicate[],
  options: PredicateAlignmentOptions,
): Promise<PredicateAlignmentResult> => {
  validateOptions(options);
  const { view, knowledge, excluded } = buildView(predicates, options.owner_account_id);
  const plan = planBatches(view, options);
  const planned = plan.planned;
  const pending = planned;
  const outcomes = await mapLimit(pending, options.model_concurrency, async (batch): Promise<PredicateAlignmentBatchOutcome> => {
    const coordinate = {
      batch_index: batch.batch_index,
      batch_question_digest: batch.digest,
      predicate_frontier: batch.request.predicate_frontier,
      predicate_ids: batch.request.predicates.map((predicate) => predicate.predicate_id),
    };
    if (batch.cost > options.batch_prompt_budget) {
      return { ...coordinate, kind: "retryable_error", error_code: "batch_prompt_budget_exceeded" };
    }
    let response: unknown;
    try {
      response = await model.invoke({
        strategy: options.adjudication_contract.strategy,
        version: options.adjudication_contract.prompt_version,
        input: batch.request,
      });
    } catch {
      return { ...coordinate, kind: "retryable_error", error_code: "model_invoke_failed" };
    }
    let proposals: readonly unknown[] | null = null;
    let response_digest: string | null = null;
    try {
      proposals = responseAssertions(response);
      if (proposals !== null && isPlainJson(response)) response_digest = sha256CanonicalRedacted(response);
    } catch {
      proposals = null;
    }
    if (proposals === null || response_digest === null) {
      return { ...coordinate, kind: "retryable_error", error_code: "model_response_invalid" };
    }
    const rejected_proposals: PredicateProposalRejection[] = [];
    let assertions: PredicateAssertion[];
    try {
      const byId = new Map<string, PredicateAssertion>();
      proposals.forEach((proposal, proposal_index) => {
        const assertion = proposalAssertion(proposal, proposal_index, batch, knowledge, rejected_proposals);
        if (assertion) byId.set(assertion.assertion_id, assertion);
      });
      assertions = [...byId.values()].sort((left, right) => compareStrings(left.assertion_id, right.assertion_id));
    } catch {
      return { ...coordinate, kind: "retryable_error", error_code: "model_response_invalid" };
    }
    const resultSeed: CanonicalJson = {
      kind: "predicate-alignment-result-v2",
      batch_question_digest: batch.digest,
      response_digest,
      assertions: assertions.map((assertion) => ({
        assertion_id: assertion.assertion_id,
        owner_account_id: assertion.owner_account_id,
        predicate_id: assertion.predicate_id,
        relation: assertion.relation,
        target_predicate_id: assertion.target_predicate_id,
        slot_aliases: assertion.slot_aliases.map((slot) => ({
          from_slot_id: slot.from_slot_id,
          to_slot_id: slot.to_slot_id,
        })),
        alias_frontier: assertion.alias_frontier,
        admission: assertion.admission,
        lifecycle: assertion.lifecycle,
        supersedes_assertion_id: assertion.supersedes_assertion_id,
      })),
      rejected_proposals: rejected_proposals.map((rejection) => ({
        proposal_index: rejection.proposal_index,
        code: rejection.code,
      })),
    };
    const result_digest = sha256CanonicalRedacted(resultSeed);
    return {
      ...coordinate,
      kind: "success",
      settleable_batch_digest: batch.digest,
      response_digest,
      result_digest,
      assertions,
      rejected_proposals,
    };
  });
  return {
    assertions: outcomes.flatMap((outcome) => outcome.kind === "success" ? outcome.assertions : [])
      .sort((left, right) => compareStrings(left.assertion_id, right.assertion_id)),
    batch_outcomes: outcomes,
    skipped_settled_batch_digests: [...new Set([
      ...plan.valid_successes.map((success) => success.batch_question_digest),
    ])].sort(compareStrings),
    excluded_predicates: excluded,
    coverage: plan.coverage,
  };
};
