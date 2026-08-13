import { describe, expect, test } from "bun:test";

import {
  DERIVED_GROUP_DREAM_VERSION,
  derivedGroupDreamPreservesOriginals,
  derivedGroupDreamProjectionContractDigest,
  planDerivedGroupDream,
} from "./derived-group-dream";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;

const dreamInput = () => ({
  version: DERIVED_GROUP_DREAM_VERSION,
  owner_account_id: "account:alice",
  input_frontier: digest("f"),
  projection_contract_digest: derivedGroupDreamProjectionContractDigest({
    strategy_version: "dream:v1",
    code_version: "code:v1",
  }),
  original_claims: [
    {
      claim_revision_id: "claim:one:r1",
      proposition_id: "proposition:one",
      evidence_ref: ref("atevidence1", "a"),
    },
    {
      claim_revision_id: "claim:two:r1",
      proposition_id: "proposition:two",
      evidence_ref: ref("atevidence1", "b"),
    },
    {
      claim_revision_id: "claim:three:r1",
      proposition_id: "proposition:three",
      evidence_ref: ref("atevidence1", "c"),
    },
  ],
  group_memberships: [{
    group_key: "group:launch-week",
    proposition_ids: ["proposition:one", "proposition:two"],
  }],
  people_cluster_beliefs: [{
    cluster_about_ref: ref("about1", "a"),
    cluster_entity_target_ref: ref("attrtarget1", "a"),
    member_evidence_refs: [ref("atevidence1", "a"), ref("atevidence1", "b")],
    belief_contract_digest: digest("1"),
    aggregation_contract_digest: digest("2"),
    calibration_contract_digest: digest("3"),
  }],
  created_at_event_time: 1_700_000_000,
});

describe("derived group dream", () => {
  test("emits rebuildable groups and probabilistic people beliefs without touching originals", () => {
    const outcome = planDerivedGroupDream(dreamInput());

    expect(outcome.original_claim_revision_ids).toEqual([
      "claim:one:r1", "claim:three:r1", "claim:two:r1",
    ]);
    expect(outcome.group_projections).toHaveLength(1);
    expect(outcome.group_projections[0]?.proposition_ids).toEqual([
      "proposition:one", "proposition:two",
    ]);
    expect(outcome.people_cluster_beliefs).toHaveLength(1);
    expect(outcome.people_cluster_beliefs[0]?.belief_kind).toBe("claim_subject");
    expect(outcome.people_cluster_beliefs[0]?.hypotheses.some((item) => item.kind === "entity")).toBeTrue();
    expect(outcome.people_cluster_beliefs[0]?.hypotheses.some((item) => item.kind === "unknown")).toBeTrue();
    expect(derivedGroupDreamPreservesOriginals(dreamInput(), outcome)).toBeTrue();
    expect(JSON.stringify(outcome)).not.toContain("subject:owner");
  });

  test("rejects unknown cluster members and single-member groups", () => {
    expect(() => planDerivedGroupDream({
      ...dreamInput(),
      group_memberships: [{
        group_key: "group:solo",
        proposition_ids: ["proposition:one"],
      }],
    })).toThrow("invalid_input");
    expect(() => planDerivedGroupDream({
      ...dreamInput(),
      people_cluster_beliefs: [{
        ...dreamInput().people_cluster_beliefs[0]!,
        member_evidence_refs: [ref("atevidence1", "z")],
      }],
    })).toThrow("invalid_input");
  });
});
