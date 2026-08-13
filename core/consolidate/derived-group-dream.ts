import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../retrieve/content-digest";
import {
  buildProductGroupProjection,
  parseProductGroupProjection,
  PRODUCT_PROJECTION_CONTRACT_VERSION,
  type ProductGroupProjection,
} from "../retrieve/product-projection";
import {
  attributionEvidenceFactorRef,
  attributionHypothesisId,
  buildAttributionBeliefRevision,
  parseAttributionBeliefRevision,
  type AttributionBeliefRevision,
} from "./attribution-belief";

export const DERIVED_GROUP_DREAM_VERSION = "derived-group-dream-v1" as const;
export const DERIVED_GROUP_DREAM_WORK_KIND = "derived_group_dream" as const;

export interface DerivedGroupDreamClaimRef {
  readonly claim_revision_id: string;
  readonly proposition_id: string;
  readonly evidence_ref: string;
}

export interface DerivedPeopleClusterBeliefInput {
  readonly cluster_about_ref: string;
  readonly cluster_entity_target_ref: string;
  readonly member_evidence_refs: readonly string[];
  readonly belief_contract_digest: string;
  readonly aggregation_contract_digest: string;
  readonly calibration_contract_digest: string;
}

export interface DerivedGroupDreamInput {
  readonly version: typeof DERIVED_GROUP_DREAM_VERSION;
  readonly owner_account_id: string;
  readonly input_frontier: string;
  readonly projection_contract_digest: string;
  readonly original_claims: readonly DerivedGroupDreamClaimRef[];
  readonly group_memberships: readonly {
    readonly group_key: string;
    readonly proposition_ids: readonly string[];
  }[];
  readonly people_cluster_beliefs: readonly DerivedPeopleClusterBeliefInput[];
  readonly created_at_event_time: number;
}

export interface DerivedGroupDreamOutcome {
  readonly version: typeof DERIVED_GROUP_DREAM_VERSION;
  readonly owner_account_id: string;
  readonly input_frontier: string;
  readonly projection_contract_digest: string;
  readonly original_claim_revision_ids: readonly string[];
  readonly group_projections: readonly ProductGroupProjection[];
  readonly people_cluster_beliefs: readonly AttributionBeliefRevision[];
  readonly result_digest: string;
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const ABOUT_REF = /^about1_[a-f0-9]{64}$/;
const TARGET_REF = /^attrtarget1_[a-f0-9]{64}$/;
const EVIDENCE_REF = /^atevidence1_[a-f0-9]{64}$/;
const MAX_MEMBERS = 128;
const MAX_GROUPS = 256;
const MAX_CLAIMS = 10_000;

const fail = (code: string): never => { throw new TypeError(`derived group dream ${code}`); };

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

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

const sortedUniqueTokens = (values: readonly string[], maximum: number, code: string): readonly string[] => {
  if (!Array.isArray(values) || isProxy(values) || values.length > maximum) fail(code);
  const sorted = [...new Set(values.map((value) => token(value, code)))].sort();
  if (sorted.length !== new Set(values).size) fail(code);
  return Object.freeze(sorted);
};

const claimRevisionId = (value: unknown, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value.length > 256) fail(code);
  return value;
};

const propositionIdToken = (value: unknown, code: string): string => token(value, code);

const claimRefs = (value: unknown, code: string): readonly DerivedGroupDreamClaimRef[] => Object.freeze(
  (Array.isArray(value) ? value : fail(code)).map((item) => {
    const input = exactRecord(item, ["claim_revision_id", "proposition_id", "evidence_ref"], code);
    return Object.freeze({
      claim_revision_id: claimRevisionId(input["claim_revision_id"], code),
      proposition_id: propositionIdToken(input["proposition_id"], code),
      evidence_ref: token(input["evidence_ref"], code),
    });
  }),
);

const peopleClusterInputs = (
  value: unknown,
  code: string,
): readonly DerivedPeopleClusterBeliefInput[] => Object.freeze(
  (Array.isArray(value) ? value : fail(code)).map((item) => {
    const input = exactRecord(item, [
      "cluster_about_ref", "cluster_entity_target_ref", "member_evidence_refs",
      "belief_contract_digest", "aggregation_contract_digest", "calibration_contract_digest",
    ], code);
    const aboutRef = token(input["cluster_about_ref"], code);
    if (!ABOUT_REF.test(aboutRef)) fail(code);
    const entityTargetRef = token(input["cluster_entity_target_ref"], code);
    if (!TARGET_REF.test(entityTargetRef)) fail(code);
    const evidenceRefs = sortedUniqueTokens(
      input["member_evidence_refs"] as readonly string[], MAX_MEMBERS, code,
    );
    if (evidenceRefs.some((evidenceRef) => !EVIDENCE_REF.test(evidenceRef))) fail(code);
    return Object.freeze({
      cluster_about_ref: aboutRef,
      cluster_entity_target_ref: entityTargetRef,
      member_evidence_refs: evidenceRefs,
      belief_contract_digest: digest(input["belief_contract_digest"], code),
      aggregation_contract_digest: digest(input["aggregation_contract_digest"], code),
      calibration_contract_digest: digest(input["calibration_contract_digest"], code),
    });
  }),
);

export const parseDerivedGroupDreamInput = (value: unknown): Readonly<DerivedGroupDreamInput> => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "input_frontier", "projection_contract_digest",
    "original_claims", "group_memberships", "people_cluster_beliefs", "created_at_event_time",
  ], "invalid_input");
  if (input["version"] !== DERIVED_GROUP_DREAM_VERSION) fail("invalid_input");
  const owner = token(input["owner_account_id"], "invalid_input");
  const originalClaims = claimRefs(input["original_claims"], "invalid_input");
  if (originalClaims.length === 0 || originalClaims.length > MAX_CLAIMS) fail("invalid_input");
  const evidenceByClaim = new Map(originalClaims.map((item) => [item.evidence_ref, item.claim_revision_id]));
  const memberships = (Array.isArray(input["group_memberships"]) ? input["group_memberships"] : fail("invalid_input"));
  if (memberships.length > MAX_GROUPS) fail("invalid_input");
  const grouped = memberships.map((item) => {
    const group = exactRecord(item, ["group_key", "proposition_ids"], "invalid_input");
    const propositionIds = sortedUniqueTokens(group["proposition_ids"] as readonly string[], MAX_MEMBERS, "invalid_input");
    if (propositionIds.length < 2) fail("invalid_input");
    return Object.freeze({
      group_key: token(group["group_key"], "invalid_input"),
      proposition_ids: propositionIds,
    });
  });
  const groupedKeys = sortedUniqueTokens(grouped.map((item) => item.group_key), MAX_GROUPS, "invalid_input");
  if (groupedKeys.length !== grouped.length) fail("invalid_input");
  const peopleClusters = peopleClusterInputs(input["people_cluster_beliefs"], "invalid_input");
  for (const cluster of peopleClusters) {
    for (const evidenceRef of cluster.member_evidence_refs) {
      if (!evidenceByClaim.has(evidenceRef)) fail("unknown_cluster_member");
    }
  }
  const createdAt = input["created_at_event_time"];
  if (!Number.isSafeInteger(createdAt) || (createdAt as number) < 0) fail("invalid_input");
  return Object.freeze({
    version: DERIVED_GROUP_DREAM_VERSION,
    owner_account_id: owner,
    input_frontier: token(input["input_frontier"], "invalid_input"),
    projection_contract_digest: digest(input["projection_contract_digest"], "invalid_input"),
    original_claims: originalClaims,
    group_memberships: Object.freeze(grouped),
    people_cluster_beliefs: peopleClusters,
    created_at_event_time: createdAt as number,
  });
};

const peopleClusterBelief = (
  input: Readonly<DerivedGroupDreamInput>,
  cluster: DerivedPeopleClusterBeliefInput,
): AttributionBeliefRevision => {
  const entityHypothesis = {
    kind: "entity" as const,
    target_ref: cluster.cluster_entity_target_ref,
    probability_micros: 600_000,
  };
  const unknownHypothesis = {
    kind: "unknown" as const,
    target_ref: null,
    probability_micros: 400_000,
  };
  const entityHypothesisId = attributionHypothesisId({
    owner_account_id: input.owner_account_id,
    belief_kind: "claim_subject",
    about_ref: cluster.cluster_about_ref,
    kind: entityHypothesis.kind,
    target_ref: entityHypothesis.target_ref,
  });
  const observationRef = `obsref1_${sha256CanonicalContent({
    contract_version: DERIVED_GROUP_DREAM_VERSION,
    cluster_about_ref: cluster.cluster_about_ref,
    input_frontier: input.input_frontier,
  })}`;
  const independenceGroupRef = `atind1_${sha256CanonicalContent({
    contract_version: DERIVED_GROUP_DREAM_VERSION,
    cluster_about_ref: cluster.cluster_about_ref,
  })}`;
  const evidenceFactors = cluster.member_evidence_refs.map((evidenceRef) => {
    const factorBody = {
      evidence_ref: evidenceRef,
      independence_group_ref: independenceGroupRef,
      hypothesis_id: entityHypothesisId,
      direction: "support" as const,
      factor_contract_digest: cluster.belief_contract_digest,
    };
    return Object.freeze({
      factor_ref: attributionEvidenceFactorRef(factorBody),
      ...factorBody,
    });
  }).sort((left, right) => left.factor_ref < right.factor_ref ? -1 : left.factor_ref > right.factor_ref ? 1 : 0);
  return parseAttributionBeliefRevision(buildAttributionBeliefRevision({
    owner_account_id: input.owner_account_id,
    belief_kind: "claim_subject",
    about_ref: cluster.cluster_about_ref,
    observation_ref: observationRef,
    observation_content_digest: sha256CanonicalContent({
      contract_version: DERIVED_GROUP_DREAM_VERSION,
      cluster_about_ref: cluster.cluster_about_ref,
      member_evidence_refs: cluster.member_evidence_refs,
      input_frontier: input.input_frontier,
    }),
    graph_frontier: input.input_frontier,
    hypotheses: [entityHypothesis, unknownHypothesis],
    evidence_factors: evidenceFactors,
    attribution_contract_digest: cluster.belief_contract_digest,
    aggregation_contract_digest: cluster.aggregation_contract_digest,
    calibration_contract_digest: cluster.calibration_contract_digest,
    created_at_event_time: input.created_at_event_time,
    previous_revision: null,
  }));
};

/**
 * Pure derived-group dream planner. It emits rebuildable groups and people
 * beliefs only; originals are referenced and never rewritten or deleted.
 */
export const planDerivedGroupDream = (
  inputValue: DerivedGroupDreamInput,
): Readonly<DerivedGroupDreamOutcome> => {
  const input = parseDerivedGroupDreamInput(inputValue);
  const originalClaimRevisionIds = sortedUniqueTokens(
    input.original_claims.map((item) => item.claim_revision_id), MAX_CLAIMS, "invalid_input",
  );
  const groupProjections = Object.freeze(input.group_memberships.map((membership) => {
    const resultDigest = sha256CanonicalContent({
      contract_version: DERIVED_GROUP_DREAM_VERSION,
      group_key: membership.group_key,
      proposition_ids: membership.proposition_ids,
      input_frontier: input.input_frontier,
    });
    return buildProductGroupProjection({
      owner_account_id: input.owner_account_id,
      proposition_ids: [...membership.proposition_ids],
      input_frontier: input.input_frontier,
      projection_contract_digest: input.projection_contract_digest,
      result_digest: resultDigest,
      created_at_event_time: input.created_at_event_time,
    });
  }));
  const peopleBeliefs = Object.freeze(input.people_cluster_beliefs.map((cluster) =>
    peopleClusterBelief(input, cluster)));
  const outcomeWithoutDigest = {
    version: DERIVED_GROUP_DREAM_VERSION,
    owner_account_id: input.owner_account_id,
    input_frontier: input.input_frontier,
    projection_contract_digest: input.projection_contract_digest,
    original_claim_revision_ids: originalClaimRevisionIds,
    group_projections: groupProjections,
    people_cluster_beliefs: peopleBeliefs,
  };
  return Object.freeze({
    ...outcomeWithoutDigest,
    result_digest: sha256CanonicalContent({
      contract_version: DERIVED_GROUP_DREAM_VERSION,
      ...outcomeWithoutDigest,
      group_projection_ids: groupProjections.map((item) => item.group_projection_id),
      people_belief_revision_ids: peopleBeliefs.map((item) => item.belief_revision_id),
    }),
  });
};

export const derivedGroupDreamPreservesOriginals = (
  input: Readonly<DerivedGroupDreamInput>,
  outcome: Readonly<DerivedGroupDreamOutcome>,
): boolean => {
  const parsed = parseDerivedGroupDreamInput(input);
  const planned = planDerivedGroupDream(parsed);
  return planned.original_claim_revision_ids.join(":") === outcome.original_claim_revision_ids.join(":")
    && planned.original_claim_revision_ids.every((claimRevisionId) =>
      parsed.original_claims.some((item) => item.claim_revision_id === claimRevisionId));
};

export const derivedGroupDreamProjectionContractDigest = (
  coordinates: Readonly<{ strategy_version: string; code_version: string }>,
): string => sha256CanonicalContent({
  contract_version: DERIVED_GROUP_DREAM_VERSION,
  product_projection_contract_version: PRODUCT_PROJECTION_CONTRACT_VERSION,
  strategy_version: coordinates.strategy_version,
  code_version: coordinates.code_version,
});

export const parseDerivedGroupDreamOutcome = (value: unknown): Readonly<DerivedGroupDreamOutcome> => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "input_frontier", "projection_contract_digest",
    "original_claim_revision_ids", "group_projections", "people_cluster_beliefs", "result_digest",
  ], "invalid_outcome");
  if (input["version"] !== DERIVED_GROUP_DREAM_VERSION) fail("invalid_outcome");
  const owner = token(input["owner_account_id"], "invalid_outcome");
  const originalClaimRevisionIds = sortedUniqueTokens(
    input["original_claim_revision_ids"] as readonly string[], MAX_CLAIMS, "invalid_outcome",
  );
  const groupProjections = (Array.isArray(input["group_projections"]) ? input["group_projections"] : fail("invalid_outcome"))
    .map((item) => parseProductGroupProjection(item));
  const peopleBeliefs = (Array.isArray(input["people_cluster_beliefs"]) ? input["people_cluster_beliefs"] : fail("invalid_outcome"))
    .map((item) => parseAttributionBeliefRevision(item));
  const resultDigest = digest(input["result_digest"], "invalid_outcome");
  const outcomeWithoutDigest = {
    version: DERIVED_GROUP_DREAM_VERSION,
    owner_account_id: owner,
    input_frontier: token(input["input_frontier"], "invalid_outcome"),
    projection_contract_digest: digest(input["projection_contract_digest"], "invalid_outcome"),
    original_claim_revision_ids: originalClaimRevisionIds,
    group_projections: Object.freeze(groupProjections),
    people_cluster_beliefs: Object.freeze(peopleBeliefs),
  };
  if (sha256CanonicalContent({
    contract_version: DERIVED_GROUP_DREAM_VERSION,
    ...outcomeWithoutDigest,
    group_projection_ids: groupProjections.map((item) => item.group_projection_id),
    people_belief_revision_ids: peopleBeliefs.map((item) => item.belief_revision_id),
  }) !== resultDigest) fail("invalid_outcome");
  return Object.freeze({ ...outcomeWithoutDigest, result_digest: resultDigest });
};
