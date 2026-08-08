import { compareStrings } from "../order";

const INTERNAL_REF = /^[\x21-\x7e]{1,512}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const STRATEGY_VERSION = /^[A-Za-z0-9._:-]{1,128}$/;

type PlainJson = null | boolean | number | string | readonly PlainJson[] | { readonly [key: string]: PlainJson };

const fail = (message: string): never => { throw new TypeError(message); };

/**
 * Detach caller-owned values before any semantic read. Data descriptors are
 * consumed exactly once; accessors, inherited/class state, sparse arrays,
 * symbols, cycles, and non-JSON values fail closed. A Proxy can execute traps
 * during inspection, but no caller object or alias survives this boundary.
 */
const detachPlainJson = (input: unknown): PlainJson => {
  const active = new WeakSet<object>();
  const copy = (value: unknown): PlainJson => {
    if (value === null || typeof value === "string" || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) return fail("recall integrity rejects non-finite numbers");
      return Object.is(value, -0) ? 0 : value;
    }
    if (typeof value !== "object") return fail("recall integrity accepts plain JSON only");
    if (active.has(value)) return fail("recall integrity rejects cycles");
    active.add(value);
    try {
      if (Array.isArray(value)) {
        const descriptors = Object.getOwnPropertyDescriptors(value);
        const keys = Reflect.ownKeys(descriptors);
        if (keys.some((key) => typeof key !== "string")) return fail("recall integrity rejects symbol keys");
        const indexKeys = keys.filter((key) => key !== "length") as string[];
        if (indexKeys.length !== value.length
          || indexKeys.some((key, index) => key !== String(index))) return fail("recall integrity rejects sparse or decorated arrays");
        const result = indexKeys.map((key) => {
          const descriptor = descriptors[key];
          if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) return fail("recall integrity rejects array accessors");
          return copy(descriptor.value);
        });
        return Object.freeze(result);
      }
      if (Object.getPrototypeOf(value) !== Object.prototype) return fail("recall integrity rejects non-plain objects");
      const descriptors = Object.getOwnPropertyDescriptors(value);
      const keys = Reflect.ownKeys(descriptors);
      if (keys.some((key) => typeof key !== "string")) return fail("recall integrity rejects symbol keys");
      const result: Record<string, PlainJson> = {};
      for (const key of (keys as string[]).sort(compareStrings)) {
        const descriptor = descriptors[key];
        if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) return fail("recall integrity rejects accessors and hidden fields");
        result[key] = copy(descriptor.value);
      }
      return Object.freeze(result);
    } catch (error) {
      if (error instanceof TypeError && error.message.startsWith("recall integrity")) throw error;
      return fail("recall integrity rejects unstable objects");
    } finally {
      active.delete(value);
    }
  };
  return copy(input);
};

const isRecord = (value: PlainJson): value is { readonly [key: string]: PlainJson } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const exactKeys = (value: PlainJson, expected: readonly string[]): value is { readonly [key: string]: PlainJson } => {
  if (!isRecord(value)) return false;
  const actual = Object.keys(value).sort(compareStrings);
  const wanted = [...expected].sort(compareStrings);
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
};

const isRef = (value: PlainJson): value is string => typeof value === "string" && INTERNAL_REF.test(value);
const uniqueStrings = (values: readonly string[]): boolean => new Set(values).size === values.length;
const sortedUnique = <Value extends string>(values: readonly Value[]): readonly Value[] =>
  Object.freeze([...new Set(values)].sort(compareStrings));

// domain-pending(DIV-DOMCORE-006)
export type RecallCandidateOrigin = "durable" | "stm" | "accepted_unprocessed";

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export interface AuthorizedRecallCandidate {
  readonly candidate_ref: string;
  readonly dedupe_ref: string;
  /** Server-owned rank within an already-decided equivalence class. */
  readonly dedupe_rank: number;
  /** Internal deterministic key; it is never part of the public projection. */
  readonly order_key: string;
  readonly origin: RecallCandidateOrigin;
  readonly frontier: string;
  readonly supersedes_refs: readonly string[];
}

// domain-pending(DIV-DOMCORE-006)
const ORIGIN_RANK: Readonly<Record<RecallCandidateOrigin, number>> = Object.freeze({
  durable: 0,
  accepted_unprocessed: 1,
  stm: 2,
});

// domain-pending(DIV-DOMCORE-006)
const parseCandidate = (value: PlainJson): AuthorizedRecallCandidate => {
  if (!exactKeys(value, ["candidate_ref", "dedupe_ref", "dedupe_rank", "order_key", "origin", "frontier", "supersedes_refs"])) {
    return fail("recall candidate has an invalid shape");
  }
  const origin = value.origin;
  if (!isRef(value.candidate_ref) || !isRef(value.dedupe_ref) || !isRef(value.order_key) || !isRef(value.frontier)
    || (origin !== "durable" && origin !== "stm" && origin !== "accepted_unprocessed")
    || typeof value.dedupe_rank !== "number" || !Number.isSafeInteger(value.dedupe_rank)
    || !Array.isArray(value.supersedes_refs) || !value.supersedes_refs.every(isRef)
    || !uniqueStrings(value.supersedes_refs) || value.supersedes_refs.includes(value.candidate_ref)) {
    return fail("recall candidate has invalid values");
  }
  return Object.freeze({
    candidate_ref: value.candidate_ref,
    dedupe_ref: value.dedupe_ref,
    dedupe_rank: value.dedupe_rank,
    order_key: value.order_key,
    origin,
    frontier: value.frontier,
    supersedes_refs: Object.freeze([...value.supersedes_refs]),
  });
};

const preferredEquivalent = (left: AuthorizedRecallCandidate, right: AuthorizedRecallCandidate): AuthorizedRecallCandidate => {
  if (left.dedupe_rank !== right.dedupe_rank) return left.dedupe_rank > right.dedupe_rank ? left : right;
  if (ORIGIN_RANK[left.origin] !== ORIGIN_RANK[right.origin]) return ORIGIN_RANK[left.origin] < ORIGIN_RANK[right.origin] ? left : right;
  return compareStrings(left.candidate_ref, right.candidate_ref) <= 0 ? left : right;
};

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export const mergeAuthorizedRecallCandidates = (input: unknown): readonly AuthorizedRecallCandidate[] => {
  const detached = detachPlainJson(input);
  if (!Array.isArray(detached)) return fail("recall candidates must be an array");
  const candidates = detached.map(parseCandidate);
  const refs = candidates.map((candidate) => candidate.candidate_ref);
  if (!uniqueStrings(refs)) return fail("recall candidates require unique references");
  const byRef = new Map(candidates.map((candidate) => [candidate.candidate_ref, candidate]));
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const assertAcyclic = (candidateRef: string): void => {
    if (visiting.has(candidateRef)) return fail("recall candidate supersession is cyclic");
    if (visited.has(candidateRef)) return;
    visiting.add(candidateRef);
    for (const supersededRef of byRef.get(candidateRef)?.supersedes_refs ?? []) {
      if (byRef.has(supersededRef)) assertAcyclic(supersededRef);
    }
    visiting.delete(candidateRef);
    visited.add(candidateRef);
  };
  for (const candidateRef of refs) assertAcyclic(candidateRef);
  const superseded = new Set(candidates.flatMap((candidate) => [...candidate.supersedes_refs]));
  const winners = new Map<string, AuthorizedRecallCandidate>();
  for (const candidate of candidates) {
    if (superseded.has(candidate.candidate_ref)) continue;
    const previous = winners.get(candidate.dedupe_ref);
    winners.set(candidate.dedupe_ref, previous ? preferredEquivalent(previous, candidate) : candidate);
  }
  return Object.freeze([...winners.values()].sort((left, right) =>
    compareStrings(left.order_key, right.order_key) || compareStrings(left.candidate_ref, right.candidate_ref)));
};

export type RecallLimitationReason =
  | "accepted_work_pending"
  | "projection_stale"
  | "projection_unavailable"
  | "projection_bypassed"
  | "source_bound"
  | "time_bound"
  | "policy_bound";

export type RecallCompletenessStatus = "complete" | "incomplete" | "degraded" | "partial";
export type RecallProjectionFreshness = "fresh" | "stale" | "unavailable" | "bypassed";
export type AcceptedCoverageState = "searched" | "no_eligible" | "pending" | "unavailable" | "stale" | "bypassed" | "source_bound" | "time_bound" | "policy_bound";
// domain-pending(DIV-DOMCORE-006)
export type StmCoverageState = Exclude<AcceptedCoverageState, "pending">;

interface CoverageInput {
  readonly state: AcceptedCoverageState | StmCoverageState;
  readonly searched_frontier: string | null;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export interface RecallCompletenessInput {
  readonly declared_frontier: string;
  readonly accepted: CoverageInput;
  readonly stm: CoverageInput & { readonly state: StmCoverageState };
  readonly projection_freshness: RecallProjectionFreshness;
  readonly intentional_bounds: readonly ("source_bound" | "time_bound" | "policy_bound")[];
}

export type MissingAcceptedFrontierReason = "no_eligible_accepted" | RecallLimitationReason;
// domain-pending(DIV-DOMCORE-006)
export type MissingStmFrontierReason = "no_eligible_stm" | Exclude<RecallLimitationReason, "accepted_work_pending">;

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export interface RecallCompletenessResult {
  readonly version: "recall-completeness-v1";
  readonly status: RecallCompletenessStatus;
  readonly reasons: readonly RecallLimitationReason[];
  readonly frontiers: {
    readonly declared_frontier: string;
    readonly newest_accepted_frontier_searched: string | null;
    readonly missing_accepted_frontier_reason: MissingAcceptedFrontierReason | null;
    readonly newest_stm_frontier_searched: string | null;
    readonly missing_stm_frontier_reason: MissingStmFrontierReason | null;
  };
}

const COVERAGE_STATES = new Set<AcceptedCoverageState>([
  "searched", "no_eligible", "pending", "unavailable", "stale", "bypassed", "source_bound", "time_bound", "policy_bound",
]);
const FRESHNESS = new Set<RecallProjectionFreshness>(["fresh", "stale", "unavailable", "bypassed"]);
const BOUNDS = new Set(["source_bound", "time_bound", "policy_bound"] as const);

const parseCoverage = (value: PlainJson, accepted: boolean): CoverageInput => {
  if (!exactKeys(value, ["state", "searched_frontier"]) || typeof value.state !== "string" || !COVERAGE_STATES.has(value.state as AcceptedCoverageState)
    || (!accepted && value.state === "pending") || (value.searched_frontier !== null && !isRef(value.searched_frontier))) {
    return fail("recall coverage has an invalid shape");
  }
  if (value.state === "searched" && value.searched_frontier === null) return fail("searched coverage requires exactly one frontier");
  if (value.state === "no_eligible" && value.searched_frontier !== null) return fail("ineligible coverage cannot claim a searched frontier");
  return Object.freeze({ state: value.state as AcceptedCoverageState, searched_frontier: value.searched_frontier as string | null });
};

const coverageReason = (state: AcceptedCoverageState): RecallLimitationReason | null => {
  if (state === "pending") return "accepted_work_pending";
  if (state === "stale") return "projection_stale";
  if (state === "unavailable") return "projection_unavailable";
  if (state === "bypassed") return "projection_bypassed";
  if (state === "source_bound" || state === "time_bound" || state === "policy_bound") return state;
  return null;
};

const missingAcceptedReason = (coverage: CoverageInput): MissingAcceptedFrontierReason | null => {
  if (coverage.searched_frontier !== null) return null;
  return coverage.state === "no_eligible" ? "no_eligible_accepted" : coverageReason(coverage.state);
};

// domain-pending(DIV-DOMCORE-006)
const missingStmReason = (coverage: CoverageInput): MissingStmFrontierReason | null => {
  if (coverage.searched_frontier !== null) return null;
  return coverage.state === "no_eligible" ? "no_eligible_stm" : coverageReason(coverage.state) as MissingStmFrontierReason;
};

const reasonStatus = (reason: RecallLimitationReason): Exclude<RecallCompletenessStatus, "complete"> => {
  if (reason === "projection_stale" || reason === "projection_unavailable" || reason === "projection_bypassed") return "degraded";
  if (reason === "accepted_work_pending") return "incomplete";
  return "partial";
};

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export const computeRecallCompleteness = (input: unknown): RecallCompletenessResult => {
  const value = detachPlainJson(input);
  if (!exactKeys(value, ["declared_frontier", "accepted", "stm", "projection_freshness", "intentional_bounds"])
    || !isRef(value.declared_frontier) || typeof value.projection_freshness !== "string"
    || !FRESHNESS.has(value.projection_freshness as RecallProjectionFreshness)
    || !Array.isArray(value.intentional_bounds) || !value.intentional_bounds.every((bound) => typeof bound === "string" && BOUNDS.has(bound as never))
    || !uniqueStrings(value.intentional_bounds as string[])) return fail("recall completeness input has an invalid shape");
  const accepted = parseCoverage(value.accepted, true);
  const stm = parseCoverage(value.stm, false);
  const reasons: RecallLimitationReason[] = [];
  if (value.projection_freshness !== "fresh") reasons.push(`projection_${value.projection_freshness}` as RecallLimitationReason);
  const acceptedReason = coverageReason(accepted.state);
  const stmReason = coverageReason(stm.state);
  if (acceptedReason) reasons.push(acceptedReason);
  if (stmReason) reasons.push(stmReason);
  reasons.push(...value.intentional_bounds as ("source_bound" | "time_bound" | "policy_bound")[]);
  const orderedReasons = sortedUnique(reasons);
  const statuses = new Set(orderedReasons.map(reasonStatus));
  const status: RecallCompletenessStatus = statuses.has("degraded") ? "degraded"
    : statuses.has("incomplete") ? "incomplete"
      : statuses.has("partial") ? "partial"
        : "complete";
  const result: RecallCompletenessResult = {
    version: "recall-completeness-v1",
    status,
    reasons: orderedReasons,
    frontiers: {
      declared_frontier: value.declared_frontier,
      newest_accepted_frontier_searched: accepted.searched_frontier,
      missing_accepted_frontier_reason: missingAcceptedReason(accepted),
      newest_stm_frontier_searched: stm.searched_frontier,
      missing_stm_frontier_reason: missingStmReason(stm),
    },
  };
  Object.freeze(result.frontiers);
  return Object.freeze(result);
};

export interface RecallAbsenceQualification {
  readonly kind: "query_gap";
  /** A limited completeness envelope qualifies this gap; it is never global absence. */
  readonly globally_complete: boolean;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export const qualifyRecallAbsence = (
  itemCount: number,
  hasMore: boolean,
  completeness: RecallCompletenessResult,
): RecallAbsenceQualification | null => {
  if (!Number.isSafeInteger(itemCount) || itemCount < 0 || typeof hasMore !== "boolean") return fail("invalid recall page state");
  if (itemCount > 0) return null;
  if (hasMore) return fail("an empty recall page cannot advertise continuation");
  return Object.freeze({ kind: "query_gap", globally_complete: completeness.status === "complete" });
};

export type RecallTraceOutcome = "grounded" | "no_eligible_candidates" | "no_selection" | "hydration_unavailable" | "policy_filtered" | "ungrounded" | "degraded";
export type RecallTraceFreshness = RecallProjectionFreshness;
export type RecallTraceRef = `tr1_${string}`;

export interface RecallTraceStages {
  readonly eligible: readonly RecallTraceRef[];
  readonly selected: readonly RecallTraceRef[];
  readonly hydrated: readonly RecallTraceRef[];
  readonly policyEligible: readonly RecallTraceRef[];
  readonly cited: readonly RecallTraceRef[];
  readonly grounded: readonly RecallTraceRef[];
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export interface ContentSafeRecallTrace {
  readonly version: "recall-trace-v1";
  readonly traceRef: RecallTraceRef;
  readonly strategyVersion: string;
  readonly projectionFreshness: RecallTraceFreshness;
  readonly outcome: RecallTraceOutcome;
  readonly latencyMs: number;
  readonly tokenCounts: { readonly input: number; readonly output: number };
  readonly stages: RecallTraceStages;
}

const TRACE_STAGE_KEYS = ["eligible", "selected", "hydrated", "policyEligible", "cited", "grounded"] as const;
const TRACE_OUTCOMES = new Set<RecallTraceOutcome>(["grounded", "no_eligible_candidates", "no_selection", "hydration_unavailable", "policy_filtered", "ungrounded", "degraded"]);

const parseTrace = (input: unknown): ContentSafeRecallTrace => {
  const value = detachPlainJson(input);
  if (!exactKeys(value, ["version", "traceRef", "strategyVersion", "projectionFreshness", "outcome", "latencyMs", "tokenCounts", "stages"])
    || value.version !== "recall-trace-v1" || typeof value.traceRef !== "string" || !TRACE_REF.test(value.traceRef)
    || typeof value.strategyVersion !== "string" || !STRATEGY_VERSION.test(value.strategyVersion)
    || typeof value.projectionFreshness !== "string" || !FRESHNESS.has(value.projectionFreshness as RecallTraceFreshness)
    || typeof value.outcome !== "string" || !TRACE_OUTCOMES.has(value.outcome as RecallTraceOutcome)
    || typeof value.latencyMs !== "number" || !Number.isSafeInteger(value.latencyMs) || value.latencyMs < 0
    || !exactKeys(value.tokenCounts, ["input", "output"]) || typeof value.tokenCounts.input !== "number" || !Number.isSafeInteger(value.tokenCounts.input) || value.tokenCounts.input < 0
    || typeof value.tokenCounts.output !== "number" || !Number.isSafeInteger(value.tokenCounts.output) || value.tokenCounts.output < 0
    || !exactKeys(value.stages, TRACE_STAGE_KEYS)) return fail("recall trace has an invalid shape");
  const stages = {} as Record<(typeof TRACE_STAGE_KEYS)[number], readonly RecallTraceRef[]>;
  for (const key of TRACE_STAGE_KEYS) {
    const refs = value.stages[key];
    if (!Array.isArray(refs) || !refs.every((ref) => typeof ref === "string" && TRACE_REF.test(ref)) || !uniqueStrings(refs as string[])) {
      return fail("recall trace contains invalid stage references");
    }
    stages[key] = Object.freeze([...(refs as RecallTraceRef[])]);
  }
  for (let index = 1; index < TRACE_STAGE_KEYS.length; index += 1) {
    const previous = new Set(stages[TRACE_STAGE_KEYS[index - 1]!]!);
    if (!stages[TRACE_STAGE_KEYS[index]!]!.every((ref) => previous.has(ref))) return fail("recall trace stages must be monotonic subsets");
  }
  const eligible = stages.eligible.length;
  const selected = stages.selected.length;
  const hydrated = stages.hydrated.length;
  const policyEligible = stages.policyEligible.length;
  const grounded = stages.grounded.length;
  const outcome = value.outcome as RecallTraceOutcome;
  const honest = outcome === "grounded" ? grounded > 0
    : outcome === "no_eligible_candidates" ? eligible === 0
      : outcome === "no_selection" ? eligible > 0 && selected === 0
        : outcome === "hydration_unavailable" ? selected > 0 && hydrated === 0
          : outcome === "policy_filtered" ? hydrated > 0 && policyEligible === 0
            : outcome === "ungrounded" ? policyEligible > 0 && grounded === 0
              : value.projectionFreshness !== "fresh" && grounded === 0;
  if (!honest) return fail("recall trace outcome contradicts its stages");
  const frozenStages = Object.freeze(stages) as unknown as RecallTraceStages;
  const tokenCounts = Object.freeze({ input: value.tokenCounts.input, output: value.tokenCounts.output });
  return Object.freeze({
    version: "recall-trace-v1",
    traceRef: value.traceRef as RecallTraceRef,
    strategyVersion: value.strategyVersion,
    projectionFreshness: value.projectionFreshness as RecallTraceFreshness,
    outcome,
    latencyMs: value.latencyMs,
    tokenCounts,
    stages: frozenStages,
  });
};

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export const buildContentSafeRecallTrace = (input: unknown): ContentSafeRecallTrace => parseTrace(input);

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export const hasContentSafeRecallTrace = (input: unknown): input is ContentSafeRecallTrace => {
  try { parseTrace(input); return true; } catch { return false; }
};

/** Telemetry is evidence only: sink failure is isolated from the read result. */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export const emitRecallTraceSafely = (
  trace: ContentSafeRecallTrace,
  sink: (trace: ContentSafeRecallTrace) => void,
): boolean => {
  const safe = parseTrace(trace);
  try { sink(safe); return true; } catch { return false; }
};
