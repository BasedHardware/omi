import { isProxy } from "node:util/types";

import { sha256CanonicalRedacted, type CanonicalJson } from "../ledger";

export const ATTRIBUTION_BELIEF_VERSION = "attribution-belief-v1" as const;
export const PROBABILITY_MICROS_TOTAL = 1_000_000 as const;

export type AttributionBeliefKind = "source_identity" | "claim_subject" | "claim_truth";
export type AttributionHypothesisKind =
  | "owner"
  | "entity"
  | "source_local"
  | "unknown"
  | "true"
  | "false";
export type AttributionEvidenceDirection = "support" | "counter";

export interface AttributionHypothesis {
  readonly hypothesis_id: string;
  readonly kind: AttributionHypothesisKind;
  readonly target_ref: string | null;
  readonly probability_micros: number;
}

export interface AttributionEvidenceFactor {
  readonly factor_ref: string;
  readonly evidence_ref: string;
  readonly independence_group_ref: string;
  readonly hypothesis_id: string;
  readonly direction: AttributionEvidenceDirection;
  readonly factor_contract_digest: string;
}

export interface AttributionBeliefRevision {
  readonly version: typeof ATTRIBUTION_BELIEF_VERSION;
  readonly owner_account_id: string;
  readonly belief_lineage_id: string;
  readonly belief_revision_id: string;
  readonly previous_belief_revision_id: string | null;
  readonly belief_kind: AttributionBeliefKind;
  readonly about_ref: string;
  readonly observation_ref: string;
  readonly observation_content_digest: string;
  readonly graph_frontier: string;
  readonly hypotheses: readonly AttributionHypothesis[];
  readonly evidence_factors: readonly AttributionEvidenceFactor[];
  readonly attribution_contract_digest: string;
  readonly aggregation_contract_digest: string;
  readonly calibration_contract_digest: string;
  readonly created_at_event_time: number;
}

export interface BuildAttributionBeliefRevisionInput {
  readonly owner_account_id: string;
  readonly belief_kind: AttributionBeliefKind;
  readonly about_ref: string;
  readonly observation_ref: string;
  readonly observation_content_digest: string;
  readonly graph_frontier: string;
  readonly hypotheses: readonly Omit<AttributionHypothesis, "hypothesis_id">[];
  readonly evidence_factors: readonly AttributionEvidenceFactor[];
  readonly attribution_contract_digest: string;
  readonly aggregation_contract_digest: string;
  readonly calibration_contract_digest: string;
  readonly created_at_event_time: number;
  readonly previous_revision: AttributionBeliefRevision | null;
}

export type AttributionBeliefContractErrorCode =
  | "invalid_attribution_belief"
  | "invalid_attribution_belief_successor";

export class AttributionBeliefContractError extends Error {
  constructor(readonly code: AttributionBeliefContractErrorCode) {
    super(code);
    this.name = "AttributionBeliefContractError";
  }
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const ABOUT_REF = /^about1_[a-f0-9]{64}$/;
const OBSERVATION_REF = /^obsref1_[a-f0-9]{64}$/;
const TARGET_REF = /^attrtarget1_[a-f0-9]{64}$/;
const HYPOTHESIS_ID = /^athyp1_[a-f0-9]{64}$/;
const FACTOR_REF = /^atfactor1_[a-f0-9]{64}$/;
const EVIDENCE_REF = /^atevidence1_[a-f0-9]{64}$/;
const INDEPENDENCE_REF = /^atind1_[a-f0-9]{64}$/;
const LINEAGE_ID = /^atbl1_[a-f0-9]{64}$/;
const REVISION_ID = /^atbr1_[a-f0-9]{64}$/;
const ARRAY_INDEX = /^(0|[1-9]\d*)$/;
const MAX_HYPOTHESES = 1_024;
const MAX_FACTORS = 10_000;

const fail = (code: AttributionBeliefContractErrorCode): never => {
  throw new AttributionBeliefContractError(code);
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
  code: AttributionBeliefContractErrorCode,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (
  value: unknown,
  maximum: number,
  code: AttributionBeliefContractErrorCode,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail(code);
  const arrayValue = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(arrayValue);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== arrayValue.length + 1) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < arrayValue.length; index += 1) {
    const key = String(index);
    const descriptor = descriptors[key];
    if (!ARRAY_INDEX.test(key) || !descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output.push(descriptor!.value);
  }
  return output;
};

const token = (value: unknown, code: AttributionBeliefContractErrorCode): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const matched = (
  value: unknown,
  pattern: RegExp,
  code: AttributionBeliefContractErrorCode,
): string => {
  if (typeof value !== "string" || !pattern.test(value)) fail(code);
  return value as string;
};

const digest = (value: unknown, code: AttributionBeliefContractErrorCode): string =>
  matched(value, DIGEST, code);

const safeEventTime = (value: unknown, code: AttributionBeliefContractErrorCode): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(code);
  return value as number;
};

const micros = (value: unknown, code: AttributionBeliefContractErrorCode): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0
    || (value as number) > PROBABILITY_MICROS_TOTAL) fail(code);
  return value as number;
};

const beliefKind = (value: unknown, code: AttributionBeliefContractErrorCode): AttributionBeliefKind => {
  if (value !== "source_identity" && value !== "claim_subject" && value !== "claim_truth") fail(code);
  return value as AttributionBeliefKind;
};

const hypothesisKind = (
  value: unknown,
  code: AttributionBeliefContractErrorCode,
): AttributionHypothesisKind => {
  if (value !== "owner" && value !== "entity" && value !== "source_local"
    && value !== "unknown" && value !== "true" && value !== "false") fail(code);
  return value as AttributionHypothesisKind;
};

const direction = (
  value: unknown,
  code: AttributionBeliefContractErrorCode,
): AttributionEvidenceDirection => {
  if (value !== "support" && value !== "counter") fail(code);
  return value as AttributionEvidenceDirection;
};

const hypothesisKey = (kind: AttributionHypothesisKind, targetRef: string | null): string =>
  `${kind}:${targetRef ?? ""}`;

const compareStrings = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

export const attributionHypothesisId = (value: {
  readonly owner_account_id: string;
  readonly belief_kind: AttributionBeliefKind;
  readonly about_ref: string;
  readonly kind: AttributionHypothesisKind;
  readonly target_ref: string | null;
}): string => `athyp1_${sha256CanonicalRedacted({
  owner_account_id: value.owner_account_id,
  belief_kind: value.belief_kind,
  about_ref: value.about_ref,
  hypothesis: value.kind,
  target_ref: value.target_ref,
})}`;

const permittedHypothesis = (
  belief: AttributionBeliefKind,
  hypothesis: AttributionHypothesisKind,
): boolean => belief === "claim_truth"
  ? hypothesis === "true" || hypothesis === "false" || hypothesis === "unknown"
  : hypothesis === "owner" || hypothesis === "entity"
    || hypothesis === "source_local" || hypothesis === "unknown";

const hypotheses = (
  value: unknown,
  owner: string,
  kind: AttributionBeliefKind,
  aboutRef: string,
  requireIds: boolean,
  code: AttributionBeliefContractErrorCode,
): readonly AttributionHypothesis[] => {
  const parsed = exactArray(value, MAX_HYPOTHESES, code).map((entry) => {
    const row = exactRecord(
      entry,
      requireIds
        ? ["hypothesis_id", "kind", "target_ref", "probability_micros"]
        : ["kind", "target_ref", "probability_micros"],
      code,
    );
    const hypothesis = hypothesisKind(row["kind"], code);
    if (!permittedHypothesis(kind, hypothesis)) fail(code);
    const targetRef = row["target_ref"] === null
      ? null
      : matched(row["target_ref"], TARGET_REF, code);
    if ((hypothesis === "entity" || hypothesis === "source_local") !== (targetRef !== null)) fail(code);
    const expectedId = attributionHypothesisId({
      owner_account_id: owner,
      belief_kind: kind,
      about_ref: aboutRef,
      kind: hypothesis,
      target_ref: targetRef,
    });
    if (requireIds && matched(row["hypothesis_id"], HYPOTHESIS_ID, code) !== expectedId) fail(code);
    return Object.freeze({
      hypothesis_id: expectedId,
      kind: hypothesis,
      target_ref: targetRef,
      probability_micros: micros(row["probability_micros"], code),
    });
  }).sort((left, right) => compareStrings(
    hypothesisKey(left.kind, left.target_ref),
    hypothesisKey(right.kind, right.target_ref),
  ));
  if (parsed.length < 2) fail(code);
  const keys = parsed.map((item) => hypothesisKey(item.kind, item.target_ref));
  if (keys.some((key, index) => index > 0 && key === keys[index - 1])) fail(code);
  if (!parsed.some((item) => item.kind === "unknown")) fail(code);
  if (kind === "claim_truth" && !parsed.some((item) => item.kind === "true")
    && !parsed.some((item) => item.kind === "false")) fail(code);
  if (parsed.reduce((total, item) => total + item.probability_micros, 0) !== PROBABILITY_MICROS_TOTAL) fail(code);
  if (requireIds) {
    const supplied = exactArray(value, MAX_HYPOTHESES, code) as readonly Record<string, unknown>[];
    if (supplied.some((item, index) => item["hypothesis_id"] !== parsed[index]?.hypothesis_id)) fail(code);
  }
  return Object.freeze(parsed);
};

const factors = (
  value: unknown,
  knownHypotheses: ReadonlySet<string>,
  code: AttributionBeliefContractErrorCode,
): readonly AttributionEvidenceFactor[] => {
  const evidenceGroups = new Map<string, string>();
  const parsed = exactArray(value, MAX_FACTORS, code).map((entry) => {
    const row = exactRecord(entry, [
      "factor_ref", "evidence_ref", "independence_group_ref", "hypothesis_id",
      "direction", "factor_contract_digest",
    ], code);
    const factorRef = matched(row["factor_ref"], FACTOR_REF, code);
    const evidenceRef = matched(row["evidence_ref"], EVIDENCE_REF, code);
    const independenceRef = matched(row["independence_group_ref"], INDEPENDENCE_REF, code);
    const hypothesis = matched(row["hypothesis_id"], HYPOTHESIS_ID, code);
    if (!knownHypotheses.has(hypothesis)) fail(code);
    const priorGroup = evidenceGroups.get(evidenceRef);
    if (priorGroup !== undefined && priorGroup !== independenceRef) fail(code);
    evidenceGroups.set(evidenceRef, independenceRef);
    const core = Object.freeze({
      evidence_ref: evidenceRef,
      independence_group_ref: independenceRef,
      hypothesis_id: hypothesis,
      direction: direction(row["direction"], code),
      factor_contract_digest: digest(row["factor_contract_digest"], code),
    });
    if (factorRef !== attributionEvidenceFactorRef(core)) fail(code);
    return Object.freeze({ factor_ref: factorRef, ...core });
  }).sort((left, right) => compareStrings(left.factor_ref, right.factor_ref));
  if (parsed.length === 0) fail(code);
  if (parsed.some((item, index) => index > 0 && item.factor_ref === parsed[index - 1]?.factor_ref)) fail(code);
  const supplied = exactArray(value, MAX_FACTORS, code) as readonly Record<string, unknown>[];
  if (supplied.some((item, index) => item["factor_ref"] !== parsed[index]?.factor_ref)) fail(code);
  return Object.freeze(parsed);
};

const lineageId = (owner: string, kind: AttributionBeliefKind, aboutRef: string): string =>
  `atbl1_${sha256CanonicalRedacted({ owner_account_id: owner, belief_kind: kind, about_ref: aboutRef })}`;

const revisionId = (value: Omit<AttributionBeliefRevision, "belief_revision_id">): string =>
  `atbr1_${sha256CanonicalRedacted(value as unknown as CanonicalJson)}`;

export const attributionEvidenceFactorRef = (
  value: Omit<AttributionEvidenceFactor, "factor_ref">,
): string => `atfactor1_${sha256CanonicalRedacted({
  evidence_ref: value.evidence_ref,
  independence_group_ref: value.independence_group_ref,
  hypothesis_id: value.hypothesis_id,
  direction: value.direction,
  factor_contract_digest: value.factor_contract_digest,
} as CanonicalJson)}`;

const parseFields = (
  value: unknown,
  code: AttributionBeliefContractErrorCode,
): AttributionBeliefRevision => {
  const row = exactRecord(value, [
    "version", "owner_account_id", "belief_lineage_id", "belief_revision_id",
    "previous_belief_revision_id", "belief_kind", "about_ref", "observation_ref",
    "observation_content_digest", "graph_frontier", "hypotheses", "evidence_factors",
    "attribution_contract_digest", "aggregation_contract_digest", "calibration_contract_digest",
    "created_at_event_time",
  ], code);
  if (row["version"] !== ATTRIBUTION_BELIEF_VERSION) fail(code);
  const owner = token(row["owner_account_id"], code);
  const kind = beliefKind(row["belief_kind"], code);
  const aboutRef = matched(row["about_ref"], ABOUT_REF, code);
  const parsedHypotheses = hypotheses(row["hypotheses"], owner, kind, aboutRef, true, code);
  const core = Object.freeze({
    version: ATTRIBUTION_BELIEF_VERSION,
    owner_account_id: owner,
    belief_lineage_id: matched(row["belief_lineage_id"], LINEAGE_ID, code),
    previous_belief_revision_id: row["previous_belief_revision_id"] === null
      ? null
      : matched(row["previous_belief_revision_id"], REVISION_ID, code),
    belief_kind: kind,
    about_ref: aboutRef,
    observation_ref: matched(row["observation_ref"], OBSERVATION_REF, code),
    observation_content_digest: digest(row["observation_content_digest"], code),
    graph_frontier: digest(row["graph_frontier"], code),
    hypotheses: parsedHypotheses,
    evidence_factors: factors(
      row["evidence_factors"],
      new Set(parsedHypotheses.map((item) => item.hypothesis_id)),
      code,
    ),
    attribution_contract_digest: digest(row["attribution_contract_digest"], code),
    aggregation_contract_digest: digest(row["aggregation_contract_digest"], code),
    calibration_contract_digest: digest(row["calibration_contract_digest"], code),
    created_at_event_time: safeEventTime(row["created_at_event_time"], code),
  });
  if (core.belief_lineage_id !== lineageId(owner, kind, aboutRef)) fail(code);
  const expectedRevisionId = revisionId(core);
  if (matched(row["belief_revision_id"], REVISION_ID, code) !== expectedRevisionId) fail(code);
  return Object.freeze({ ...core, belief_revision_id: expectedRevisionId });
};

export const parseAttributionBeliefRevision = (value: unknown): AttributionBeliefRevision =>
  parseFields(value, "invalid_attribution_belief");

export const assertAttributionBeliefSuccessor = (
  previous: AttributionBeliefRevision,
  next: AttributionBeliefRevision,
): void => {
  const code = "invalid_attribution_belief_successor" as const;
  const prior = parseFields(previous, code);
  const successor = parseFields(next, code);
  if (successor.belief_lineage_id !== prior.belief_lineage_id
    || successor.previous_belief_revision_id !== prior.belief_revision_id
    || successor.observation_ref !== prior.observation_ref
    || successor.observation_content_digest !== prior.observation_content_digest
    || successor.created_at_event_time < prior.created_at_event_time) fail(code);
};

export const buildAttributionBeliefRevision = (
  value: BuildAttributionBeliefRevisionInput,
): AttributionBeliefRevision => {
  const code = "invalid_attribution_belief" as const;
  const row = exactRecord(value, [
    "owner_account_id", "belief_kind", "about_ref", "observation_ref",
    "observation_content_digest", "graph_frontier", "hypotheses", "evidence_factors",
    "attribution_contract_digest", "aggregation_contract_digest", "calibration_contract_digest",
    "created_at_event_time", "previous_revision",
  ], code);
  const owner = token(row["owner_account_id"], code);
  const kind = beliefKind(row["belief_kind"], code);
  const aboutRef = matched(row["about_ref"], ABOUT_REF, code);
  const parsedHypotheses = hypotheses(row["hypotheses"], owner, kind, aboutRef, false, code);
  const previous = row["previous_revision"] === null
    ? null
    : parseFields(row["previous_revision"], code);
  const core = Object.freeze({
    version: ATTRIBUTION_BELIEF_VERSION,
    owner_account_id: owner,
    belief_lineage_id: lineageId(owner, kind, aboutRef),
    previous_belief_revision_id: previous?.belief_revision_id ?? null,
    belief_kind: kind,
    about_ref: aboutRef,
    observation_ref: matched(row["observation_ref"], OBSERVATION_REF, code),
    observation_content_digest: digest(row["observation_content_digest"], code),
    graph_frontier: digest(row["graph_frontier"], code),
    hypotheses: parsedHypotheses,
    evidence_factors: factors(
      row["evidence_factors"],
      new Set(parsedHypotheses.map((item) => item.hypothesis_id)),
      code,
    ),
    attribution_contract_digest: digest(row["attribution_contract_digest"], code),
    aggregation_contract_digest: digest(row["aggregation_contract_digest"], code),
    calibration_contract_digest: digest(row["calibration_contract_digest"], code),
    created_at_event_time: safeEventTime(row["created_at_event_time"], code),
  });
  const result = Object.freeze({ ...core, belief_revision_id: revisionId(core) });
  if (previous !== null) assertAttributionBeliefSuccessor(previous, result);
  return result;
};
