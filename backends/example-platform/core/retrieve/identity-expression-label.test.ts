import { describe, expect, test } from "bun:test";

import { planPeopleClusterBeliefs } from "../consolidate/derived-group-dream";
import {
  identityExpressionLabelForBelief,
  identityExpressionLabelsForBeliefs,
  ratifiedIdentityExpressionClass,
} from "./identity-expression-label";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;

describe("identity expression labels", () => {
  test("emits source_local and never certain_owner from people beliefs", () => {
    const beliefs = planPeopleClusterBeliefs({
      owner_account_id: "account:alice",
      input_frontier: digest("f"),
      created_at_event_time: 1,
    }, [{
      cluster_about_ref: ref("about1", "a"),
      cluster_entity_target_ref: ref("attrtarget1", "b"),
      member_evidence_refs: [ref("atevidence1", "c")],
      belief_contract_digest: digest("1"),
      aggregation_contract_digest: digest("2"),
      calibration_contract_digest: digest("3"),
    }]);
    const labels = identityExpressionLabelsForBeliefs(beliefs);
    expect(labels).toHaveLength(1);
    expect(labels[0]?.label).toBe("source_local");
    expect(labels[0]?.label).not.toBe("certain_owner");
    expect(identityExpressionLabelForBelief(beliefs[0]!).owner_probability_micros).toBe(0);
  });
});

describe("ratified expression class mapping", () => {
  test("certain voice splits on the grader's owner determination", () => {
    expect(ratifiedIdentityExpressionClass("certain_owner", true)).toBe("certain_owner_match");
    expect(ratifiedIdentityExpressionClass("certain_owner", false)).toBe("certain_owner_mismatch");
    // A certain-voice row without a determination is a programming error, not
    // a defensible abstention.
    expect(() => ratifiedIdentityExpressionClass("certain_owner", null))
      .toThrow("certain_owner_requires_grader_determination");
  });

  test("clarification_required grades as qualified, never abstain", () => {
    expect(ratifiedIdentityExpressionClass("clarification_required", null)).toBe("qualified");
  });

  test("the remaining machine labels are already ratified class names", () => {
    expect(ratifiedIdentityExpressionClass("qualified", null)).toBe("qualified");
    expect(ratifiedIdentityExpressionClass("source_local", null)).toBe("source_local");
    expect(ratifiedIdentityExpressionClass("abstain", null)).toBe("abstain");
  });
});
