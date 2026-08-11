// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-005)
import { expect, test } from "bun:test";

import {
  isPlacementDecision,
  MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
  parseFormationOutcomeEnvelope,
  retainsAcceptedWork,
} from "./formation-outcome";

const coordinates = () => ({
  contract_version: MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
  strategy_version: "grounded-reference-v1",
  model_version: "deterministic-fake-v1",
  prompt_version: "none",
  policy_version: "fixture-policy-v1",
  code_version: "memory-productionization-v1",
  schema_version: "memory-productionization-comparison-v1",
  tokenizer_version: "none",
  tool_version: "synthetic-fixture-v1",
  speaker_strategy_version: "session-frame-reference-v1",
  boundary_strategy_version: "unit-boundary-reference-v1",
});

const envelope = () => ({
  contract_version: MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
  owner_account_id: "owner:synthetic",
  work_id: "work:synthetic:1",
  input_frontier: "frontier:synthetic:1",
  coordinates: coordinates(),
  extraction_outcomes: [
    {
      kind: "accepted",
      candidate_ref: "candidate:accepted",
      claim_revision_id: "claim:provisional:accepted",
      evidence_ids: ["evidence:2", "evidence:1"],
      repair_codes: ["surface_case_normalized"],
    },
    {
      kind: "accepted",
      candidate_ref: "candidate:error",
      claim_revision_id: "claim:provisional:error",
      evidence_ids: ["evidence:1"],
      repair_codes: [],
    },
    {
      kind: "dropped",
      candidate_ref: "candidate:dropped",
      reason_code: "missing_argument",
      reason_detail: "object",
    },
  ],
  placement_outcomes: [
    {
      kind: "admitted",
      input_provisional_revision_id: "claim:provisional:accepted",
      canonical_claim_revision_id: "claim:canonical:accepted",
      boundary_decision: "accept_ltm",
      scope_locality: "durable",
    },
    {
      kind: "retryable_error",
      input_provisional_revision_id: "claim:provisional:error",
      attempt: 1,
      max_attempts: 3,
      error_code: "model_timeout",
      next_eligible_at: null,
    },
  ],
});

test("P1 formation outcome is detached, canonicalized, frozen, and fully versioned", () => {
  const mutable = envelope();
  const parsed = parseFormationOutcomeEnvelope(mutable);
  expect(parsed.coordinates).toEqual(coordinates());
  expect(parsed.extraction_outcomes[0]).toMatchObject({
    evidence_ids: ["evidence:1", "evidence:2"],
    repair_codes: ["surface_case_normalized"],
  });
  expect(Object.isFrozen(parsed)).toBe(true);
  expect(Object.isFrozen(parsed.coordinates)).toBe(true);
  expect(Object.isFrozen(parsed.extraction_outcomes)).toBe(true);
  expect(Object.isFrozen(parsed.extraction_outcomes[0])).toBe(true);
  mutable.owner_account_id = "owner:mutated";
  mutable.extraction_outcomes[0]!.evidence_ids[0] = "evidence:mutated";
  expect(parsed.owner_account_id).toBe("owner:synthetic");
  expect(parsed.extraction_outcomes[0]).toMatchObject({ evidence_ids: ["evidence:1", "evidence:2"] });
});

test("P1 model errors retain accepted work and are never placement decisions", () => {
  const parsed = parseFormationOutcomeEnvelope(envelope());
  const admitted = parsed.placement_outcomes[0]!;
  const errored = parsed.placement_outcomes[1]!;
  expect(isPlacementDecision(admitted)).toBe(true);
  expect(retainsAcceptedWork(admitted)).toBe(false);
  expect(isPlacementDecision(errored)).toBe(false);
  expect(retainsAcceptedWork(errored)).toBe(true);
  expect(errored).toEqual({
    kind: "retryable_error",
    input_provisional_revision_id: "claim:provisional:error",
    attempt: 1,
    max_attempts: 3,
    error_code: "model_timeout",
    next_eligible_at: null,
  });
  expect(Object.keys(errored)).not.toContain("canonical_claim_revision_id");
  expect(Object.keys(errored)).not.toContain("boundary_decision");
});

test("P1 exhausted errors become retained dead work, not a fabricated abstention", () => {
  const input = envelope();
  input.placement_outcomes[1] = {
    kind: "dead_letter",
    input_provisional_revision_id: "claim:provisional:error",
    attempts: 3,
    max_attempts: 3,
    error_code: "model_timeout",
  } as never;
  const outcome = parseFormationOutcomeEnvelope(input).placement_outcomes[1]!;
  expect(outcome.kind).toBe("dead_letter");
  expect(isPlacementDecision(outcome)).toBe(false);
  expect(retainsAcceptedWork(outcome)).toBe(true);
  expect(Object.keys(outcome)).not.toContain("canonical_claim_revision_id");
  expect(Object.keys(outcome)).not.toContain("boundary_decision");
});

test("P1 formation contract rejects error/decision ambiguity and exhausted retry lies", () => {
  const exhaustedRetry = envelope();
  exhaustedRetry.placement_outcomes[1]!.attempt = 3;
  expect(() => parseFormationOutcomeEnvelope(exhaustedRetry)).toThrow("must be dead_letter");

  const prematureDead = envelope();
  prematureDead.placement_outcomes[1] = {
    kind: "dead_letter",
    input_provisional_revision_id: "claim:provisional:error",
    attempts: 2,
    max_attempts: 3,
    error_code: "model_timeout",
  } as never;
  expect(() => parseFormationOutcomeEnvelope(prematureDead)).toThrow("retry budget remaining");

  const decisionSmuggling = envelope();
  Object.assign(decisionSmuggling.placement_outcomes[1]!, {
    boundary_decision: "abstain",
  });
  expect(() => parseFormationOutcomeEnvelope(decisionSmuggling)).toThrow("invalid shape");
});

test("P1 formation contract rejects unaccepted placement, duplicates, extras, accessors, and proxies", () => {
  const unaccepted = envelope();
  unaccepted.placement_outcomes[1]!.input_provisional_revision_id = "claim:missing";
  expect(() => parseFormationOutcomeEnvelope(unaccepted)).toThrow("must reference an accepted extraction");

  const duplicate = envelope();
  duplicate.extraction_outcomes[1]!.candidate_ref = "candidate:accepted";
  expect(() => parseFormationOutcomeEnvelope(duplicate)).toThrow("candidate_ref values must be unique");

  const extra = { ...envelope(), extra: true };
  expect(() => parseFormationOutcomeEnvelope(extra)).toThrow("invalid shape");

  let getterCalls = 0;
  const accessor = envelope();
  Object.defineProperty(accessor, "owner_account_id", {
    enumerable: true,
    get: () => { getterCalls += 1; return "owner:synthetic"; },
  });
  expect(() => parseFormationOutcomeEnvelope(accessor)).toThrow("data properties");
  expect(getterCalls).toBe(0);

  expect(() => parseFormationOutcomeEnvelope(new Proxy(envelope(), {}))).toThrow("plain record");
});
