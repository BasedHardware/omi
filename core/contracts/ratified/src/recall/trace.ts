declare const RecallTraceRefBrand: unique symbol;

/** Content-free opaque handle used only to correlate recall pipeline decisions. */
export type RecallTraceRef = string & { readonly [RecallTraceRefBrand]: true };

const TRACE_REF_PATTERN = /^[\x21-\x7e]{1,1024}$/;

export function parseRecallTraceRef(raw: string): RecallTraceRef | null {
  return TRACE_REF_PATTERN.test(raw) ? (raw as RecallTraceRef) : null;
}

export type RecallTraceOutcome =
  | "grounded"
  | "no_eligible_candidates"
  | "no_selection"
  | "hydration_unavailable"
  | "policy_filtered"
  | "ungrounded"
  | "degraded";

export type ProjectionFreshness = "fresh" | "stale" | "unavailable" | "bypassed";

export interface RecallTraceV1 {
  version: "recall-trace-v1";
  traceRef: RecallTraceRef;
  strategyVersion: string;
  projectionFreshness: ProjectionFreshness;
  outcome: RecallTraceOutcome;
  latencyMs: number;
  tokenCounts: {
    input: number;
    output: number;
  };
  stages: {
    eligible: readonly RecallTraceRef[];
    selected: readonly RecallTraceRef[];
    hydrated: readonly RecallTraceRef[];
    policyEligible: readonly RecallTraceRef[];
    cited: readonly RecallTraceRef[];
    grounded: readonly RecallTraceRef[];
  };
}

export function hasSafeRecallTrace(value: unknown): value is RecallTraceV1 {
  if (!hasExactKeys(value, ["version", "traceRef", "strategyVersion", "projectionFreshness", "outcome", "latencyMs", "tokenCounts", "stages"])) return false;
  const trace = value as {
    version: unknown; traceRef: unknown; strategyVersion: unknown; projectionFreshness: unknown;
    outcome: unknown; latencyMs: unknown; tokenCounts: unknown; stages: unknown;
  };
  if (trace.version !== "recall-trace-v1" || typeof trace.traceRef !== "string" || !TRACE_REF_PATTERN.test(trace.traceRef)) return false;
  if (typeof trace.strategyVersion !== "string" || trace.strategyVersion.trim().length === 0) return false;
  if (!PROJECTION_FRESHNESS.has(trace.projectionFreshness) || !TRACE_OUTCOMES.has(trace.outcome)) return false;
  if (!isNonnegativeSafeInteger(trace.latencyMs)) return false;
  if (!hasExactKeys(trace.tokenCounts, ["input", "output"])) return false;
  const tokenCounts = trace.tokenCounts as { input: unknown; output: unknown };
  if (!isNonnegativeSafeInteger(tokenCounts.input) || !isNonnegativeSafeInteger(tokenCounts.output)) return false;
  if (!hasExactKeys(trace.stages, TRACE_STAGE_KEYS)) return false;
  const stages = trace.stages as Record<(typeof TRACE_STAGE_KEYS)[number], unknown>;
  if (!TRACE_STAGE_KEYS.every((key) => {
    const refs = stages[key];
    return Array.isArray(refs)
      && refs.every((ref) => typeof ref === "string" && TRACE_REF_PATTERN.test(ref))
      && new Set(refs).size === refs.length;
  })) return false;
  for (let index = 1; index < TRACE_STAGE_KEYS.length; index += 1) {
    const previous = new Set(stages[TRACE_STAGE_KEYS[index - 1]!] as string[]);
    const current = stages[TRACE_STAGE_KEYS[index]!] as string[];
    if (!current.every((ref) => previous.has(ref))) return false;
  }
  const eligible = stages.eligible as string[];
  const grounded = stages.grounded as string[];
  if (trace.outcome === "grounded" && grounded.length === 0) return false;
  if (trace.outcome === "no_eligible_candidates" && eligible.length !== 0) return false;
  return true;
}

const TRACE_STAGE_KEYS = ["eligible", "selected", "hydrated", "policyEligible", "cited", "grounded"] as const;
const TRACE_OUTCOMES = new Set<unknown>(["grounded", "no_eligible_candidates", "no_selection", "hydration_unavailable", "policy_filtered", "ungrounded", "degraded"]);
const PROJECTION_FRESHNESS = new Set<unknown>(["fresh", "stale", "unavailable", "bypassed"]);

function hasExactKeys(value: unknown, expected: readonly string[]): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && [...expected].sort().every((key, index) => key === actual[index]);
}

function isNonnegativeSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
