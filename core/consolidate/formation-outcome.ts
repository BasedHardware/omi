// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-005)
import { isProxy } from "node:util/types";

export const MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION = "memory-formation-outcome-v1" as const;

export interface FormationStrategyCoordinates {
  readonly contract_version: typeof MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION;
  readonly strategy_version: string;
  readonly model_version: string;
  readonly prompt_version: string;
  readonly policy_version: string;
  readonly code_version: string;
  readonly schema_version: string;
  readonly tokenizer_version: string;
  readonly tool_version: string;
  readonly speaker_strategy_version: string;
  readonly boundary_strategy_version: string;
}

export type ExtractionOutcome = Readonly<{
  kind: "accepted";
  candidate_ref: string;
  claim_revision_id: string;
  evidence_ids: readonly string[];
  repair_codes: readonly string[];
}> | Readonly<{
  kind: "dropped";
  candidate_ref: string;
  reason_code: string;
  reason_detail: string | null;
}>;

export type PlacementOutcome = Readonly<{
  kind: "admitted";
  input_provisional_revision_id: string;
  canonical_claim_revision_id: string;
  boundary_decision: "accept_ltm";
  scope_locality: "durable" | "source_local";
}> | Readonly<{
  kind: "abstained";
  input_provisional_revision_id: string;
  boundary_decision: "abstain";
  reason_code: string;
  reconsideration_trigger: string | null;
}> | Readonly<{
  kind: "retryable_error";
  input_provisional_revision_id: string;
  attempt: number;
  max_attempts: number;
  error_code: string;
  next_eligible_at: string | null;
}> | Readonly<{
  kind: "dead_letter";
  input_provisional_revision_id: string;
  attempts: number;
  max_attempts: number;
  error_code: string;
}>;

export interface FormationOutcomeEnvelope {
  readonly contract_version: typeof MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly work_id: string;
  readonly input_frontier: string;
  readonly coordinates: Readonly<FormationStrategyCoordinates>;
  readonly extraction_outcomes: readonly ExtractionOutcome[];
  readonly placement_outcomes: readonly PlacementOutcome[];
}

const ASCII_TOKEN = /^[\x21-\x7e]{1,256}$/;
const ERROR_CODE = /^[a-z][a-z0-9_.-]{0,127}$/;
const ARRAY_INDEX = /^(0|[1-9]\d*)$/;

const fail = (message: string): never => { throw new TypeError(`formation outcome ${message}`); };

const record = (value: unknown, label: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) {
    return fail(`${label} must be a plain record`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return fail(`${label} must be a plain record`);
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key === "symbol")) return fail(`${label} rejects symbol keys`);
  for (const key of keys as string[]) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      return fail(`${label} requires enumerable own data properties`);
    }
  }
  return value as Record<string, unknown>;
};

const array = (value: unknown, label: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    return fail(`${label} must be a plain array`);
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key === "symbol")) return fail(`${label} rejects symbol keys`);
  const stringKeys = keys as string[];
  if (stringKeys.length !== value.length + 1
    || stringKeys.some((key) => key !== "length" && (!ARRAY_INDEX.test(key) || Number(key) >= value.length))) {
    return fail(`${label} rejects decorated or sparse arrays`);
  }
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      return fail(`${label} requires enumerable own data elements`);
    }
  }
  return value;
};

const exactKeys = (value: Record<string, unknown>, expected: readonly string[], label: string): void => {
  const actual = Object.keys(value).sort();
  const sorted = [...expected].sort();
  if (actual.length !== sorted.length || actual.some((key, index) => key !== sorted[index])) {
    fail(`${label} has an invalid shape`);
  }
};

const token = (value: unknown, label: string): string => {
  if (typeof value !== "string" || !ASCII_TOKEN.test(value)) return fail(`${label} must be printable ASCII`);
  return value;
};

const code = (value: unknown, label: string): string => {
  if (typeof value !== "string" || !ERROR_CODE.test(value)) return fail(`${label} must be a stable code`);
  return value;
};

const nullableToken = (value: unknown, label: string): string | null =>
  value === null ? null : token(value, label);

const positiveInteger = (value: unknown, label: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1) return fail(`${label} must be a positive safe integer`);
  return value as number;
};

const tokenArray = (value: unknown, label: string): readonly string[] => {
  const parsed = array(value, label).map((item, index) => token(item, `${label}[${index}]`));
  if (new Set(parsed).size !== parsed.length) return fail(`${label} must be unique`);
  return Object.freeze([...parsed].sort());
};

const freezeRecord = <Value extends object>(value: Value): Readonly<Value> => Object.freeze(value);

const parseCoordinates = (value: unknown): Readonly<FormationStrategyCoordinates> => {
  const input = record(value, "coordinates");
  exactKeys(input, [
    "contract_version", "strategy_version", "model_version", "prompt_version",
    "policy_version", "code_version", "schema_version", "tokenizer_version",
    "tool_version", "speaker_strategy_version", "boundary_strategy_version",
  ], "coordinates");
  if (input.contract_version !== MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION) {
    fail("coordinates contract_version is unsupported");
  }
  return freezeRecord({
    contract_version: MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
    strategy_version: token(input.strategy_version, "coordinates.strategy_version"),
    model_version: token(input.model_version, "coordinates.model_version"),
    prompt_version: token(input.prompt_version, "coordinates.prompt_version"),
    policy_version: token(input.policy_version, "coordinates.policy_version"),
    code_version: token(input.code_version, "coordinates.code_version"),
    schema_version: token(input.schema_version, "coordinates.schema_version"),
    tokenizer_version: token(input.tokenizer_version, "coordinates.tokenizer_version"),
    tool_version: token(input.tool_version, "coordinates.tool_version"),
    speaker_strategy_version: token(input.speaker_strategy_version, "coordinates.speaker_strategy_version"),
    boundary_strategy_version: token(input.boundary_strategy_version, "coordinates.boundary_strategy_version"),
  });
};

const parseExtractionOutcome = (value: unknown, index: number): ExtractionOutcome => {
  const label = `extraction_outcomes[${index}]`;
  const input = record(value, label);
  if (input.kind === "accepted") {
    exactKeys(input, ["kind", "candidate_ref", "claim_revision_id", "evidence_ids", "repair_codes"], label);
    const evidenceIds = tokenArray(input.evidence_ids, `${label}.evidence_ids`);
    if (evidenceIds.length === 0) fail(`${label}.evidence_ids must not be empty`);
    return freezeRecord({
      kind: "accepted" as const,
      candidate_ref: token(input.candidate_ref, `${label}.candidate_ref`),
      claim_revision_id: token(input.claim_revision_id, `${label}.claim_revision_id`),
      evidence_ids: evidenceIds,
      repair_codes: tokenArray(input.repair_codes, `${label}.repair_codes`),
    });
  }
  if (input.kind === "dropped") {
    exactKeys(input, ["kind", "candidate_ref", "reason_code", "reason_detail"], label);
    return freezeRecord({
      kind: "dropped" as const,
      candidate_ref: token(input.candidate_ref, `${label}.candidate_ref`),
      reason_code: code(input.reason_code, `${label}.reason_code`),
      reason_detail: nullableToken(input.reason_detail, `${label}.reason_detail`),
    });
  }
  return fail(`${label}.kind is unsupported`);
};

const parsePlacementOutcome = (value: unknown, index: number): PlacementOutcome => {
  const label = `placement_outcomes[${index}]`;
  const input = record(value, label);
  if (input.kind === "admitted") {
    exactKeys(input, ["kind", "input_provisional_revision_id", "canonical_claim_revision_id", "boundary_decision", "scope_locality"], label);
    if (input.boundary_decision !== "accept_ltm") fail(`${label}.boundary_decision must be accept_ltm`);
    if (input.scope_locality !== "durable" && input.scope_locality !== "source_local") fail(`${label}.scope_locality is unsupported`);
    return freezeRecord({
      kind: "admitted" as const,
      input_provisional_revision_id: token(input.input_provisional_revision_id, `${label}.input_provisional_revision_id`),
      canonical_claim_revision_id: token(input.canonical_claim_revision_id, `${label}.canonical_claim_revision_id`),
      boundary_decision: "accept_ltm" as const,
      scope_locality: input.scope_locality,
    });
  }
  if (input.kind === "abstained") {
    exactKeys(input, ["kind", "input_provisional_revision_id", "boundary_decision", "reason_code", "reconsideration_trigger"], label);
    if (input.boundary_decision !== "abstain") fail(`${label}.boundary_decision must be abstain`);
    return freezeRecord({
      kind: "abstained" as const,
      input_provisional_revision_id: token(input.input_provisional_revision_id, `${label}.input_provisional_revision_id`),
      boundary_decision: "abstain" as const,
      reason_code: code(input.reason_code, `${label}.reason_code`),
      reconsideration_trigger: nullableToken(input.reconsideration_trigger, `${label}.reconsideration_trigger`),
    });
  }
  if (input.kind === "retryable_error") {
    exactKeys(input, ["kind", "input_provisional_revision_id", "attempt", "max_attempts", "error_code", "next_eligible_at"], label);
    const attempt = positiveInteger(input.attempt, `${label}.attempt`);
    const maxAttempts = positiveInteger(input.max_attempts, `${label}.max_attempts`);
    if (attempt >= maxAttempts) fail(`${label} is exhausted and must be dead_letter`);
    return freezeRecord({
      kind: "retryable_error" as const,
      input_provisional_revision_id: token(input.input_provisional_revision_id, `${label}.input_provisional_revision_id`),
      attempt,
      max_attempts: maxAttempts,
      error_code: code(input.error_code, `${label}.error_code`),
      next_eligible_at: nullableToken(input.next_eligible_at, `${label}.next_eligible_at`),
    });
  }
  if (input.kind === "dead_letter") {
    exactKeys(input, ["kind", "input_provisional_revision_id", "attempts", "max_attempts", "error_code"], label);
    const attempts = positiveInteger(input.attempts, `${label}.attempts`);
    const maxAttempts = positiveInteger(input.max_attempts, `${label}.max_attempts`);
    if (attempts < maxAttempts) fail(`${label} has retry budget remaining`);
    return freezeRecord({
      kind: "dead_letter" as const,
      input_provisional_revision_id: token(input.input_provisional_revision_id, `${label}.input_provisional_revision_id`),
      attempts,
      max_attempts: maxAttempts,
      error_code: code(input.error_code, `${label}.error_code`),
    });
  }
  return fail(`${label}.kind is unsupported`);
};

/**
 * Detaches, validates, canonicalizes and freezes one formation result.
 *
 * A retryable/dead model failure is deliberately not a placement decision. It
 * retains accepted work for replay and carries no canonical allocation. Only
 * `admitted` and `abstained` mean the boundary actually answered.
 */
export const parseFormationOutcomeEnvelope = (value: unknown): Readonly<FormationOutcomeEnvelope> => {
  const input = record(value, "envelope");
  exactKeys(input, [
    "contract_version", "owner_account_id", "work_id", "input_frontier", "coordinates",
    "extraction_outcomes", "placement_outcomes",
  ], "envelope");
  if (input.contract_version !== MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION) fail("contract_version is unsupported");
  const extractionOutcomes = array(input.extraction_outcomes, "extraction_outcomes")
    .map(parseExtractionOutcome);
  const placementOutcomes = array(input.placement_outcomes, "placement_outcomes")
    .map(parsePlacementOutcome);
  const candidateRefs = extractionOutcomes.map((outcome) => outcome.candidate_ref);
  if (new Set(candidateRefs).size !== candidateRefs.length) fail("candidate_ref values must be unique");
  const acceptedClaimIds = extractionOutcomes.flatMap((outcome) =>
    outcome.kind === "accepted" ? [outcome.claim_revision_id] : []);
  if (new Set(acceptedClaimIds).size !== acceptedClaimIds.length) fail("accepted claim_revision_id values must be unique");
  const placementInputIds = placementOutcomes.map((outcome) => outcome.input_provisional_revision_id);
  if (new Set(placementInputIds).size !== placementInputIds.length) fail("placement input ids must be unique");
  const accepted = new Set(acceptedClaimIds);
  if (placementInputIds.some((id) => !accepted.has(id))) fail("placement input must reference an accepted extraction");
  const canonicalIds = placementOutcomes.flatMap((outcome) =>
    outcome.kind === "admitted" ? [outcome.canonical_claim_revision_id] : []);
  if (new Set(canonicalIds).size !== canonicalIds.length) fail("canonical allocations must be unique");
  return freezeRecord({
    contract_version: MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
    owner_account_id: token(input.owner_account_id, "owner_account_id"),
    work_id: token(input.work_id, "work_id"),
    input_frontier: token(input.input_frontier, "input_frontier"),
    coordinates: parseCoordinates(input.coordinates),
    extraction_outcomes: Object.freeze(extractionOutcomes),
    placement_outcomes: Object.freeze(placementOutcomes),
  });
};

export const isPlacementDecision = (outcome: PlacementOutcome): boolean =>
  outcome.kind === "admitted" || outcome.kind === "abstained";

export const retainsAcceptedWork = (outcome: PlacementOutcome): boolean =>
  outcome.kind === "retryable_error" || outcome.kind === "dead_letter";
