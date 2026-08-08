import { describe, expect, test } from "bun:test";

import {
  buildContentSafeRecallTrace,
  computeRecallCompleteness,
  emitRecallTraceSafely,
  hasContentSafeRecallTrace,
  mergeAuthorizedRecallCandidates,
  qualifyRecallAbsence,
  type AuthorizedRecallCandidate,
  type RecallCompletenessInput,
} from "./recall-integrity";

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
const candidate = (overrides: Partial<AuthorizedRecallCandidate> = {}): AuthorizedRecallCandidate => ({
  candidate_ref: "candidate:a",
  dedupe_ref: "equivalence:a",
  dedupe_rank: 1,
  order_key: "001",
  origin: "durable",
  frontier: "frontier:durable:1",
  supersedes_refs: [],
  ...overrides,
});

// domain-pending(DIV-DOMCORE-006)
const coverage = (overrides: Partial<RecallCompletenessInput> = {}): RecallCompletenessInput => ({
  declared_frontier: "frontier:declared:1",
  accepted: { state: "no_eligible", searched_frontier: null },
  stm: { state: "no_eligible", searched_frontier: null },
  projection_freshness: "fresh",
  intentional_bounds: [],
  ...overrides,
});

const ref = (digit: string): `tr1_${string}` => `tr1_${digit.repeat(64)}`;

const groundedTrace = () => ({
  version: "recall-trace-v1" as const,
  traceRef: ref("a"),
  strategyVersion: "strategy-v1",
  projectionFreshness: "fresh" as const,
  outcome: "grounded" as const,
  latencyMs: 12,
  tokenCounts: { input: 3, output: 2 },
  stages: {
    eligible: [ref("1"), ref("2")],
    selected: [ref("1")],
    hydrated: [ref("1")],
    policyEligible: [ref("1")],
    cited: [ref("1")],
    grounded: [ref("1")],
  },
});

describe("merged authorized recent recall", () => {
  test("deduplicates and supersedes deterministically while preserving server order", () => {
    const durable = candidate({ candidate_ref: "candidate:durable", dedupe_ref: "same", dedupe_rank: 3, order_key: "020" });
    const accepted = candidate({ candidate_ref: "candidate:accepted", dedupe_ref: "same", dedupe_rank: 3, origin: "accepted_unprocessed", order_key: "010" });
    const stm = candidate({ candidate_ref: "candidate:stm", dedupe_ref: "other", origin: "stm", order_key: "030" });
    const precursor = candidate({ candidate_ref: "candidate:precursor", dedupe_ref: "precursor", origin: "stm", order_key: "000" });
    const successor = candidate({ candidate_ref: "candidate:successor", dedupe_ref: "successor", origin: "accepted_unprocessed", order_key: "005", supersedes_refs: [precursor.candidate_ref] });

    const forward = mergeAuthorizedRecallCandidates([stm, accepted, precursor, durable, successor]);
    const reverse = mergeAuthorizedRecallCandidates([successor, durable, precursor, accepted, stm]);

    expect(forward.map((item) => item.candidate_ref)).toEqual(["candidate:successor", "candidate:durable", "candidate:stm"]);
    expect(reverse).toEqual(forward);
    expect(Object.isFrozen(forward)).toBe(true);
    expect(Object.isFrozen(forward[0]!)).toBe(true);
  });

  test("rejects duplicate references, accessors, inherited objects, and decorated arrays before reuse", () => {
    expect(() => mergeAuthorizedRecallCandidates([candidate(), candidate()])).toThrow("unique references");
    expect(() => mergeAuthorizedRecallCandidates([
      candidate({ candidate_ref: "candidate:a", dedupe_ref: "a", supersedes_refs: ["candidate:b"] }),
      candidate({ candidate_ref: "candidate:b", dedupe_ref: "b", supersedes_refs: ["candidate:a"] }),
    ])).toThrow("cyclic");
    expect(() => mergeAuthorizedRecallCandidates([
      candidate({ candidate_ref: "candidate:a", dedupe_ref: "g1", dedupe_rank: 2, supersedes_refs: ["candidate:b"] }),
      candidate({ candidate_ref: "candidate:d", dedupe_ref: "g1", dedupe_rank: 1 }),
      candidate({ candidate_ref: "candidate:b", dedupe_ref: "g2", dedupe_rank: 1 }),
      candidate({ candidate_ref: "candidate:c", dedupe_ref: "g2", dedupe_rank: 2, supersedes_refs: ["candidate:d"] }),
    ])).toThrow("cyclic");

    let getterCalls = 0;
    const hostile = { ...candidate() } as Record<string, unknown>;
    Object.defineProperty(hostile, "candidate_ref", {
      enumerable: true,
      get() { getterCalls += 1; return "candidate:hostile"; },
    });
    expect(() => mergeAuthorizedRecallCandidates([hostile])).toThrow("accessors");
    expect(getterCalls).toBe(0);

    class CandidateClass { candidate_ref = "candidate:class"; }
    expect(() => mergeAuthorizedRecallCandidates([new CandidateClass()])).toThrow("non-plain");

    const decorated = [candidate()];
    Object.defineProperty(decorated, "4294967295", { enumerable: true, value: "raw sentinel" });
    expect(() => mergeAuthorizedRecallCandidates(decorated)).toThrow("decorated arrays");
  });
});

// domain-pending(DIV-DOMCORE-006)
describe("aggregate accepted and STM completeness", () => {
  test("distinguishes complete durable-only, STM hits, and accepted-unprocessed hits", () => {
    const durableOnly = computeRecallCompleteness(coverage());
    expect(durableOnly).toEqual({
      version: "recall-completeness-v1",
      status: "complete",
      reasons: [],
      frontiers: {
        declared_frontier: "frontier:declared:1",
        newest_accepted_frontier_searched: null,
        missing_accepted_frontier_reason: "no_eligible_accepted",
        newest_stm_frontier_searched: null,
        missing_stm_frontier_reason: "no_eligible_stm",
      },
    });

    const stmHit = computeRecallCompleteness(coverage({ stm: { state: "searched", searched_frontier: "frontier:stm:2" } }));
    expect(stmHit.status).toBe("complete");
    expect(stmHit.frontiers.newest_stm_frontier_searched).toBe("frontier:stm:2");

    const acceptedHit = computeRecallCompleteness(coverage({ accepted: { state: "searched", searched_frontier: "frontier:accepted:3" } }));
    expect(acceptedHit.status).toBe("complete");
    expect(acceptedHit.frontiers.newest_accepted_frontier_searched).toBe("frontier:accepted:3");
  });

  test("uses degraded then incomplete then partial precedence and keeps both frontiers honest", () => {
    const incomplete = computeRecallCompleteness(coverage({ accepted: { state: "pending", searched_frontier: null } }));
    expect(incomplete.status).toBe("incomplete");
    expect(incomplete.reasons).toEqual(["accepted_work_pending"]);
    expect(incomplete.frontiers.missing_accepted_frontier_reason).toBe("accepted_work_pending");

    const degraded = computeRecallCompleteness(coverage({
      accepted: { state: "pending", searched_frontier: "frontier:accepted:partial" },
      stm: { state: "unavailable", searched_frontier: null },
      intentional_bounds: ["time_bound"],
    }));
    expect(degraded.status).toBe("degraded");
    expect(degraded.reasons).toEqual(["accepted_work_pending", "projection_unavailable", "time_bound"]);
    expect(degraded.frontiers.newest_accepted_frontier_searched).toBe("frontier:accepted:partial");
    expect(degraded.frontiers.missing_stm_frontier_reason).toBe("projection_unavailable");

    const partial = computeRecallCompleteness(coverage({ intentional_bounds: ["policy_bound", "source_bound"] }));
    expect(partial.status).toBe("partial");
    expect(partial.reasons).toEqual(["policy_bound", "source_bound"]);
  });

  test("qualifies limited gaps and never permits an empty continuation", () => {
    const complete = computeRecallCompleteness(coverage());
    const incomplete = computeRecallCompleteness(coverage({ accepted: { state: "pending", searched_frontier: null } }));
    expect(qualifyRecallAbsence(0, false, complete)).toEqual({ kind: "query_gap", globally_complete: true });
    expect(qualifyRecallAbsence(0, false, incomplete)).toEqual({ kind: "query_gap", globally_complete: false });
    expect(qualifyRecallAbsence(1, true, incomplete)).toBeNull();
    expect(() => qualifyRecallAbsence(0, true, incomplete)).toThrow("cannot advertise continuation");
    expect(() => qualifyRecallAbsence(0, false, { ...incomplete, status: "complete" })).toThrow("requires computed completeness");
  });

  test("rejects contradictory coverage instead of silently claiming completeness", () => {
    expect(() => computeRecallCompleteness(coverage({ accepted: { state: "searched", searched_frontier: null } }))).toThrow("exactly one frontier");
    expect(() => computeRecallCompleteness(coverage({ stm: { state: "pending", searched_frontier: null } as never }))).toThrow("invalid shape");
    expect(() => computeRecallCompleteness({ ...coverage(), raw_query: "sentinel" })).toThrow("invalid shape");
  });
});

describe("content-safe recall trace", () => {
  test("builds a detached immutable eligible-to-grounded trace", () => {
    const input = groundedTrace();
    const trace = buildContentSafeRecallTrace(input);
    input.stages.eligible.push(ref("3"));
    expect(trace.stages.eligible).toEqual([ref("1"), ref("2")]);
    expect(Object.isFrozen(trace)).toBe(true);
    expect(Object.isFrozen(trace.stages)).toBe(true);
    expect(hasContentSafeRecallTrace(trace)).toBe(true);
  });

  test("rejects stage contradictions, duplicates, raw content, and undeclared fields", () => {
    expect(hasContentSafeRecallTrace({ ...groundedTrace(), outcome: "no_selection" })).toBe(false);
    expect(hasContentSafeRecallTrace({
      ...groundedTrace(),
      stages: { ...groundedTrace().stages, selected: [ref("3")] },
    })).toBe(false);
    expect(hasContentSafeRecallTrace({
      ...groundedTrace(),
      stages: { ...groundedTrace().stages, eligible: [ref("1"), ref("1")] },
    })).toBe(false);
    expect(hasContentSafeRecallTrace({
      ...groundedTrace(),
      stages: { ...groundedTrace().stages, grounded: ["raw-query-or-evidence-sentinel"] },
    })).toBe(false);
    expect(hasContentSafeRecallTrace({ ...groundedTrace(), query: "raw query sentinel" })).toBe(false);
  });

  test("rejects prototype and proxy aliases instead of certifying caller-owned telemetry", () => {
    const prototypePayload = groundedTrace() as Record<string, unknown>;
    Object.defineProperty(prototypePayload, "__proto__", {
      enumerable: true,
      value: { raw_query: "secret" },
    });
    expect(() => buildContentSafeRecallTrace(prototypePayload)).toThrow("invalid shape");
    expect(hasContentSafeRecallTrace(prototypePayload)).toBe(false);

    let exposeRaw = false;
    const proxy = new Proxy(groundedTrace() as Record<string, unknown>, {
      ownKeys(target) {
        return exposeRaw ? [...Reflect.ownKeys(target), "raw_query"] : Reflect.ownKeys(target);
      },
      getOwnPropertyDescriptor(target, property) {
        if (property === "raw_query") return { configurable: true, enumerable: true, value: "secret", writable: false };
        return Reflect.getOwnPropertyDescriptor(target, property);
      },
      get(target, property, receiver) {
        if (property === "raw_query" && exposeRaw) return "secret";
        return Reflect.get(target, property, receiver);
      },
    });
    expect(hasContentSafeRecallTrace(proxy)).toBe(false);
    exposeRaw = true;
    expect(JSON.stringify(proxy)).toContain("raw_query");
  });

  test("rejects accessors without executing them and isolates sync and async telemetry sink failures", async () => {
    let getterCalls = 0;
    const hostile = groundedTrace() as Record<string, unknown>;
    Object.defineProperty(hostile, "tokenCounts", {
      enumerable: true,
      get() { getterCalls += 1; return { input: 1, output: 1 }; },
    });
    expect(hasContentSafeRecallTrace(hostile)).toBe(false);
    expect(getterCalls).toBe(0);

    const trace = buildContentSafeRecallTrace(groundedTrace());
    const result = { id: "unchanged-result" };
    expect(await emitRecallTraceSafely(trace, () => { throw new Error("sink unavailable"); })).toBe(false);
    expect(await emitRecallTraceSafely(trace, async () => { throw new Error("async sink unavailable"); })).toBe(false);
    expect(await emitRecallTraceSafely(trace, async () => {})).toBe(true);
    expect(result).toEqual({ id: "unchanged-result" });
  });
});
