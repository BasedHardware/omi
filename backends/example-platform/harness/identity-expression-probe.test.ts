import { describe, expect, test } from "bun:test";

import {
  attributionEvidenceFactorRef,
  attributionHypothesisId,
  buildAttributionBeliefRevision,
} from "../core/consolidate/attribution-belief";
import {
  identityExpressionLabelForBelief,
  ratifiedIdentityExpressionClass,
} from "../core/retrieve/identity-expression-label";
import {
  probeIdentityExpressionLabel,
  probeIdentityExpressionLabels,
} from "./identity-expression-probe";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;

const OWNER = "account:probe";
const ABOUT = ref("about1", "a");

/** A `claim_subject` belief carrying an explicit owner mass. */
const beliefWithOwnerMass = (ownerMicros: number) => {
  const hypotheses = [
    { kind: "owner" as const, target_ref: null, probability_micros: ownerMicros },
    { kind: "unknown" as const, target_ref: null, probability_micros: 1_000_000 - ownerMicros },
  ];
  const hypothesisId = (kind: "owner" | "unknown"): string => attributionHypothesisId({
    owner_account_id: OWNER, belief_kind: "claim_subject", about_ref: ABOUT,
    kind, target_ref: null,
  });
  const core = {
    evidence_ref: ref("atevidence1", "a"),
    independence_group_ref: ref("atind1", "a"),
    hypothesis_id: hypothesisId("owner"),
    direction: "support" as const,
    factor_contract_digest: digest("2"),
  };
  return buildAttributionBeliefRevision({
    owner_account_id: OWNER,
    belief_kind: "claim_subject",
    about_ref: ABOUT,
    observation_ref: ref("obsref1", "a"),
    observation_content_digest: digest("3"),
    graph_frontier: digest("7"),
    hypotheses,
    evidence_factors: [{ factor_ref: attributionEvidenceFactorRef(core), ...core }],
    attribution_contract_digest: digest("4"),
    aggregation_contract_digest: digest("5"),
    calibration_contract_digest: digest("6"),
    created_at_event_time: 10,
    previous_revision: null,
  });
};

const PROBE = { certain_voice_threshold_micros: 980_000 } as const;

describe("evaluation-only certain-voice probe arm", () => {
  test("makes the identity floor reachable: a high-owner belief becomes certain voice", () => {
    const assignment = probeIdentityExpressionLabel(beliefWithOwnerMass(990_000), PROBE);
    expect(assignment.label).toBe("certain_owner");
    expect(assignment.probe_forced_certain_voice).toBe(true);
    expect(assignment.owner_probability_micros).toBe(990_000);
  });

  test("a certain-voice row can therefore grade as a MISMATCH, which is the whole point", () => {
    const assignment = probeIdentityExpressionLabel(beliefWithOwnerMass(990_000), PROBE);
    // This is the class ADR-015's machine rule blocks on. Before this arm
    // existed nothing could produce it, so the floor could not fail and a
    // graded sheet measured nothing.
    expect(ratifiedIdentityExpressionClass(assignment.label, false)).toBe("certain_owner_mismatch");
    expect(ratifiedIdentityExpressionClass(assignment.label, true)).toBe("certain_owner_match");
  });

  test("the shipping labeler still refuses certain voice for the very same belief", () => {
    const belief = beliefWithOwnerMass(990_000);
    // Production posture is unchanged: the arm does not relax it, it sits beside it.
    expect(identityExpressionLabelForBelief(belief).label).toBe("source_local");
    expect(probeIdentityExpressionLabel(belief, PROBE).label).toBe("certain_owner");
  });

  test("below the probe threshold the shipping labeler decides", () => {
    const assignment = probeIdentityExpressionLabel(beliefWithOwnerMass(10_000), PROBE);
    expect(assignment.label).toBe("source_local");
    expect(assignment.probe_forced_certain_voice).toBe(false);
  });

  test("zero owner mass cannot reach certain voice at any threshold", () => {
    // This is the dream path's situation. The dream planner refuses to emit a
    // belief carrying an `owner` hypothesis at all, so `owner?.probability_micros
    // ?? 0` is 0 there; this fixture reaches the same 0 with an explicit zero.
    // Either way the arm cannot manufacture certain voice from dream output,
    // even with the threshold set as low as it can go.
    const assignment = probeIdentityExpressionLabel(
      beliefWithOwnerMass(0), { certain_voice_threshold_micros: 1 },
    );
    expect(assignment.owner_probability_micros).toBe(0);
    expect(assignment.label).toBe("source_local");
  });

  test("the threshold is required and bounded, so no product default can leak in", () => {
    const belief = beliefWithOwnerMass(990_000);
    for (const bad of [0, -1, 1_000_001, 1.5, Number.NaN]) {
      expect(() => probeIdentityExpressionLabel(
        belief, { certain_voice_threshold_micros: bad },
      )).toThrow("invalid_certain_voice_threshold");
    }
    expect(() => probeIdentityExpressionLabel(belief, {} as never))
      .toThrow("invalid_certain_voice_threshold");
  });

  test("labels a batch", () => {
    const labels = probeIdentityExpressionLabels(
      [beliefWithOwnerMass(990_000), beliefWithOwnerMass(1_000)], PROBE,
    );
    expect(labels.map((item) => item.label)).toEqual(["certain_owner", "source_local"]);
  });
});
