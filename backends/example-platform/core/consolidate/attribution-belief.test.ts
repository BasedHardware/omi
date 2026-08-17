import { describe, expect, test } from "bun:test";

import {
  ATTRIBUTION_BELIEF_VERSION,
  AttributionBeliefContractError,
  assertAttributionBeliefSuccessor,
  attributionEvidenceFactorRef,
  attributionHypothesisId,
  buildAttributionBeliefRevision,
  parseAttributionBeliefRevision,
  type AttributionBeliefContractErrorCode,
  type AttributionBeliefRevision,
  type BuildAttributionBeliefRevisionInput,
} from "./attribution-belief";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;

const hypothesisId = (revision: AttributionBeliefRevision, kind: string): string =>
  revision.hypotheses.find((item) => item.kind === kind)!.hypothesis_id;

const factor = (
  value: Omit<AttributionBeliefRevision["evidence_factors"][number], "factor_ref">,
): AttributionBeliefRevision["evidence_factors"][number] => ({
  factor_ref: attributionEvidenceFactorRef(value),
  ...value,
});

const baseInput = (patch: Partial<BuildAttributionBeliefRevisionInput> = {}): BuildAttributionBeliefRevisionInput => {
  const value: BuildAttributionBeliefRevisionInput = {
    owner_account_id: "owner-a",
    belief_kind: "source_identity",
    about_ref: ref("about1", "a"),
    observation_ref: ref("obsref1", "b"),
    observation_content_digest: digest("c"),
    graph_frontier: digest("7"),
    hypotheses: [
      { kind: "owner", target_ref: null, probability_micros: 700_000 },
      { kind: "unknown", target_ref: null, probability_micros: 300_000 },
    ],
    evidence_factors: [],
    attribution_contract_digest: digest("d"),
    aggregation_contract_digest: digest("e"),
    calibration_contract_digest: digest("f"),
    created_at_event_time: 10,
    previous_revision: null,
    ...patch,
  };
  if (patch.evidence_factors !== undefined) return value;
  const primary = value.hypotheses.find((item) => item.kind !== "unknown")!;
  const hypothesis_id = attributionHypothesisId({
    owner_account_id: value.owner_account_id,
    belief_kind: value.belief_kind,
    about_ref: value.about_ref,
    kind: primary.kind,
    target_ref: primary.target_ref,
  });
  return {
    ...value,
    evidence_factors: [factor({
      evidence_ref: ref("atevidence1", "a"),
      independence_group_ref: ref("atind1", "a"),
      hypothesis_id,
      direction: "support",
      factor_contract_digest: digest("a"),
    })],
  };
};

const expectCode = (code: AttributionBeliefContractErrorCode, operation: () => unknown): void => {
  try {
    operation();
    throw new Error("expected attribution belief contract error");
  } catch (error) {
    expect(error).toBeInstanceOf(AttributionBeliefContractError);
    expect((error as AttributionBeliefContractError).code).toBe(code);
    expect((error as Error).message).toBe(code);
  }
};

describe("probabilistic attribution belief revisions", () => {
  test("builds a frozen content-addressed plane-agnostic belief with an exact probability distribution", () => {
    const first = buildAttributionBeliefRevision(baseInput());
    const replay = buildAttributionBeliefRevision(baseInput());
    expect(first).toEqual(replay);
    expect(first.version).toBe(ATTRIBUTION_BELIEF_VERSION);
    expect(first.belief_lineage_id).toMatch(/^atbl1_[a-f0-9]{64}$/);
    expect(first.belief_revision_id).toMatch(/^atbr1_[a-f0-9]{64}$/);
    expect(first.hypotheses.reduce((sum, item) => sum + item.probability_micros, 0)).toBe(1_000_000);
    expect(parseAttributionBeliefRevision(first)).toEqual(first);
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.hypotheses)).toBe(true);
    expect(Object.isFrozen(first.hypotheses[0])).toBe(true);
    for (const forbidden of ["action", "permission", "approval", "consequence", "threshold", "answer_text", "shadow", "authoritative"]) {
      expect(JSON.stringify(first)).not.toContain(forbidden);
    }
  });

  test("keeps source, subject, and truth beliefs distinct without forcing owner or discard", () => {
    const source = buildAttributionBeliefRevision(baseInput());
    const subject = buildAttributionBeliefRevision(baseInput({
      belief_kind: "claim_subject",
      hypotheses: [
        { kind: "entity", target_ref: ref("attrtarget1", "1"), probability_micros: 450_000 },
        { kind: "owner", target_ref: null, probability_micros: 350_000 },
        { kind: "unknown", target_ref: null, probability_micros: 200_000 },
      ],
    }));
    const truth = buildAttributionBeliefRevision(baseInput({
      belief_kind: "claim_truth",
      hypotheses: [
        { kind: "false", target_ref: null, probability_micros: 100_000 },
        { kind: "true", target_ref: null, probability_micros: 750_000 },
        { kind: "unknown", target_ref: null, probability_micros: 150_000 },
      ],
    }));
    expect(new Set([source.belief_lineage_id, subject.belief_lineage_id, truth.belief_lineage_id]).size).toBe(3);
    expect(subject.hypotheses.map((item) => item.kind)).toEqual(["entity", "owner", "unknown"]);
    expect(truth.hypotheses.map((item) => item.kind)).toEqual(["false", "true", "unknown"]);
  });

  test("binds content-safe evidence factors to known hypotheses and consistent independence groups", () => {
    const withoutFactors = buildAttributionBeliefRevision(baseInput());
    const ownerHypothesis = hypothesisId(withoutFactors, "owner");
    const withFactors = buildAttributionBeliefRevision(baseInput({
      evidence_factors: [
        factor({
          evidence_ref: ref("atevidence1", "2"),
          independence_group_ref: ref("atind1", "3"),
          hypothesis_id: ownerHypothesis,
          direction: "support",
          factor_contract_digest: digest("4"),
        }),
        factor({
          evidence_ref: ref("atevidence1", "2"),
          independence_group_ref: ref("atind1", "3"),
          hypothesis_id: ownerHypothesis,
          direction: "counter",
          factor_contract_digest: digest("6"),
        }),
      ].sort((left, right) => left.factor_ref < right.factor_ref ? -1 : 1),
    }));
    expect(withFactors.evidence_factors).toHaveLength(2);
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({
      evidence_factors: withFactors.evidence_factors.map((item, index) => index === 1
        ? factor({
          evidence_ref: item.evidence_ref,
          independence_group_ref: ref("atind1", "7"),
          hypothesis_id: item.hypothesis_id,
          direction: item.direction,
          factor_contract_digest: item.factor_contract_digest,
        })
        : item).sort((left, right) => left.factor_ref < right.factor_ref ? -1 : 1),
    })));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({
      evidence_factors: [factor({
        evidence_ref: withFactors.evidence_factors[0]!.evidence_ref,
        independence_group_ref: withFactors.evidence_factors[0]!.independence_group_ref,
        hypothesis_id: ref("athyp1", "9"),
        direction: withFactors.evidence_factors[0]!.direction,
        factor_contract_digest: withFactors.evidence_factors[0]!.factor_contract_digest,
      })],
    })));
  });

  test("append-only correction can lower owner belief without rewriting the observation", () => {
    const previous = buildAttributionBeliefRevision(baseInput());
    const next = buildAttributionBeliefRevision(baseInput({
      hypotheses: [
        { kind: "owner", target_ref: null, probability_micros: 200_000 },
        { kind: "unknown", target_ref: null, probability_micros: 800_000 },
      ],
      graph_frontier: digest("8"),
      created_at_event_time: 11,
      previous_revision: previous,
    }));
    expect(next.previous_belief_revision_id).toBe(previous.belief_revision_id);
    expect(next.observation_ref).toBe(previous.observation_ref);
    expect(next.observation_content_digest).toBe(previous.observation_content_digest);
    expect(hypothesisId(next, "owner")).toBe(hypothesisId(previous, "owner"));
    assertAttributionBeliefSuccessor(previous, next);
    expectCode("invalid_attribution_belief_successor", () => assertAttributionBeliefSuccessor(next, previous));
    expectCode("invalid_attribution_belief_successor", () => buildAttributionBeliefRevision(baseInput({
      about_ref: ref("about1", "9"), previous_revision: previous,
    })));
    expectCode("invalid_attribution_belief_successor", () => buildAttributionBeliefRevision(baseInput({
      observation_ref: ref("obsref1", "9"), previous_revision: previous,
    })));
  });

  test("every immutable coordinate is covered by the revision identity", () => {
    const base = buildAttributionBeliefRevision(baseInput());
    for (const changed of [
      buildAttributionBeliefRevision(baseInput({ owner_account_id: "owner-b" })),
      buildAttributionBeliefRevision(baseInput({ observation_ref: ref("obsref1", "8") })),
      buildAttributionBeliefRevision(baseInput({ observation_content_digest: digest("8") })),
      buildAttributionBeliefRevision(baseInput({ graph_frontier: digest("8") })),
      buildAttributionBeliefRevision(baseInput({ calibration_contract_digest: digest("8") })),
      buildAttributionBeliefRevision(baseInput({ created_at_event_time: 11 })),
    ]) expect(changed.belief_revision_id).not.toBe(base.belief_revision_id);
  });

  test("invalid distributions, hypotheses, targets, refs, and forged identities fail closed", () => {
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({ evidence_factors: [] })));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({
      hypotheses: [{ kind: "owner", target_ref: null, probability_micros: 1_000_000 }],
    })));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({
      hypotheses: [
        { kind: "owner", target_ref: null, probability_micros: 600_000 },
        { kind: "unknown", target_ref: null, probability_micros: 300_000 },
      ],
    })));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({
      belief_kind: "claim_truth",
      hypotheses: [
        { kind: "owner", target_ref: null, probability_micros: 500_000 },
        { kind: "unknown", target_ref: null, probability_micros: 500_000 },
      ],
    })));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({
      hypotheses: [
        { kind: "entity", target_ref: null, probability_micros: 500_000 },
        { kind: "unknown", target_ref: null, probability_micros: 500_000 },
      ],
    })));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(baseInput({
      observation_ref: "raw-transcript-or-name",
    })));
    const valid = buildAttributionBeliefRevision(baseInput());
    expectCode("invalid_attribution_belief", () => parseAttributionBeliefRevision({
      ...valid, belief_revision_id: ref("atbr1", "0"),
    }));
  });

  test("hostile, accessor, sparse, decorated, extra, and oversized data fails content-safely", () => {
    const input = baseInput();
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(new Proxy(input, {}) as never));
    const getter = { ...input } as Record<string, unknown>;
    Object.defineProperty(getter, "graph_frontier", { enumerable: true, get: () => digest("7") });
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(getter as never));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision(Object.assign(Object.create(null), input)));
    const sparse = [input.hypotheses[0], , input.hypotheses[1]];
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision({ ...input, hypotheses: sparse } as never));
    const decorated = [...input.hypotheses] as unknown[] & { raw_secret?: string };
    decorated.raw_secret = "do-not-log";
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision({ ...input, hypotheses: decorated } as never));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision({ ...input, raw_text: "secret" } as never));
    expectCode("invalid_attribution_belief", () => buildAttributionBeliefRevision({
      ...input,
      hypotheses: Array.from({ length: 1_025 }, (_, index) => ({
        kind: index === 0 ? "unknown" as const : "entity" as const,
        target_ref: index === 0 ? null : ref("attrtarget1", (index % 10).toString()),
        probability_micros: 0,
      })),
    }));
  });
});
