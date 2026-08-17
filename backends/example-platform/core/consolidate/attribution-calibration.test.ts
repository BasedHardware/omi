import { describe, expect, test } from "bun:test";

import { attributionEvidenceFactorRef, type AttributionEvidenceFactor } from "./attribution-belief";
import {
  ATTRIBUTION_CALIBRATION_RECEIPT_VERSION,
  AttributionCalibrationError,
  attributionCalibrationRequestDigest,
  calibrateAttributionBelief,
  hypothesisIdForCalibrationCandidate,
  type AttributionCalibrationErrorCode,
  type AttributionCalibrationRequest,
  type CalibrateAttributionBeliefInput,
} from "./attribution-calibration";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;
const candidates = [
  { kind: "owner" as const, target_ref: null },
  { kind: "unknown" as const, target_ref: null },
];

const base = (): Omit<CalibrateAttributionBeliefInput, "evidence_factors"> => ({
  owner_account_id: "owner-a",
  belief_kind: "source_identity",
  about_ref: ref("about1", "a"),
  observation_ref: ref("obsref1", "b"),
  observation_content_digest: digest("c"),
  graph_frontier: digest("1"),
  hypothesis_candidates: candidates,
  attribution_contract_digest: digest("d"),
  aggregation_contract_digest: digest("e"),
  calibration_contract_digest: digest("f"),
  created_at_event_time: 10,
  previous_revision: null,
});

const factor = (
  input: Omit<AttributionEvidenceFactor, "factor_ref">,
): AttributionEvidenceFactor => ({ factor_ref: attributionEvidenceFactorRef(input), ...input });

const factors = (): readonly AttributionEvidenceFactor[] => {
  const input = base();
  const owner = hypothesisIdForCalibrationCandidate(input, candidates[0]!);
  return [
    factor({
      evidence_ref: ref("atevidence1", "1"), independence_group_ref: ref("atind1", "1"),
      hypothesis_id: owner, direction: "support", factor_contract_digest: digest("1"),
    }),
    factor({
      evidence_ref: ref("atevidence1", "2"), independence_group_ref: ref("atind1", "1"),
      hypothesis_id: owner, direction: "support", factor_contract_digest: digest("2"),
    }),
    factor({
      evidence_ref: ref("atevidence1", "3"), independence_group_ref: ref("atind1", "3"),
      hypothesis_id: owner, direction: "counter", factor_contract_digest: digest("3"),
    }),
  ].sort((left, right) => left.factor_ref < right.factor_ref ? -1 : 1);
};

const expectCode = async (code: AttributionCalibrationErrorCode, operation: () => Promise<unknown>): Promise<void> => {
  try {
    await operation();
    throw new Error("expected attribution calibration error");
  } catch (error) {
    expect(error).toBeInstanceOf(AttributionCalibrationError);
    expect((error as AttributionCalibrationError).code).toBe(code);
    expect((error as Error).message).toBe(code);
  }
};

describe("dependency-aware attribution calibration seam", () => {
  test("groups dependent factors before one injected calibrator call and returns an opaque receipt", async () => {
    const seen: AttributionCalibrationRequest[] = [];
    const input = { ...base(), evidence_factors: factors() };
    const output = await calibrateAttributionBelief(input, {
      calibrate: async (request) => {
        seen.push(request);
        return { probabilities: request.hypotheses.map((item, index) => ({
          hypothesis_id: item.hypothesis_id,
          probability_micros: index === 0 ? 700_000 : 300_000,
        })) };
      },
    });
    expect(seen).toHaveLength(1);
    expect(seen[0]!.evidence_groups).toHaveLength(2);
    expect(seen[0]!.evidence_groups.map((group) => group.factors.length).sort()).toEqual([1, 2]);
    expect(seen[0]!.owner_scope_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.stringify(seen[0])).not.toContain("owner-a");
    expect(Object.isFrozen(seen[0])).toBe(true);
    expect(Object.isFrozen(seen[0]!.evidence_groups[0]!.factors)).toBe(true);
    expect(output.belief.hypotheses.map((item) => item.probability_micros)).toEqual([700_000, 300_000]);
    expect(output.receipt.version).toBe(ATTRIBUTION_CALIBRATION_RECEIPT_VERSION);
    expect(output.receipt.request_digest).toBe(attributionCalibrationRequestDigest(input));
    expect(output.receipt.belief_revision_id).toBe(output.belief.belief_revision_id);
    for (const value of [output.receipt.request_digest, output.receipt.response_digest, output.receipt.result_digest]) {
      expect(value).toMatch(/^[a-f0-9]{64}$/);
    }
  });

  test("same exact input and calibrated output are byte-stable", async () => {
    const input = { ...base(), evidence_factors: factors() };
    const calibrator = { calibrate: async (request: AttributionCalibrationRequest) => ({
      probabilities: request.hypotheses.map((item, index) => ({
        hypothesis_id: item.hypothesis_id, probability_micros: index === 0 ? 600_000 : 400_000,
      })),
    }) };
    expect(JSON.stringify(await calibrateAttributionBelief(input, calibrator)))
      .toBe(JSON.stringify(await calibrateAttributionBelief(input, calibrator)));
  });

  test("invalid input fails before a calibrator call", async () => {
    let calls = 0;
    await expectCode("invalid_attribution_calibration_input", () => calibrateAttributionBelief({
      ...base(), observation_ref: "raw observation text", evidence_factors: factors(),
    }, { calibrate: async () => { calls += 1; return {}; } }));
    expect(calls).toBe(0);
    await expectCode("invalid_attribution_calibration_input", () => calibrateAttributionBelief(
      new Proxy({ ...base(), evidence_factors: factors() }, {}) as never,
      { calibrate: async () => { calls += 1; return {}; } },
    ));
    const getter = { ...base(), evidence_factors: factors() } as Record<string, unknown>;
    Object.defineProperty(getter, "observation_ref", {
      enumerable: true,
      get: () => { throw new Error("must not execute"); },
    });
    await expectCode("invalid_attribution_calibration_input", () => calibrateAttributionBelief(
      getter as never,
      { calibrate: async () => { calls += 1; return {}; } },
    ));
    expect(calls).toBe(0);
  });

  test("missing, reordered, duplicate, malformed, and non-total outputs fail closed", async () => {
    const input = { ...base(), evidence_factors: factors() };
    const requests: AttributionCalibrationRequest[] = [];
    const run = (produce: (request: AttributionCalibrationRequest) => unknown) =>
      calibrateAttributionBelief(input, { calibrate: async (request) => {
        requests.push(request);
        return produce(request);
      } });
    await expectCode("invalid_attribution_calibration_output", () => run(() => ({ probabilities: [] })));
    await expectCode("invalid_attribution_calibration_output", () => run((request) => ({ probabilities: [
      { hypothesis_id: request.hypotheses[1]!.hypothesis_id, probability_micros: 500_000 },
      { hypothesis_id: request.hypotheses[0]!.hypothesis_id, probability_micros: 500_000 },
    ] })));
    await expectCode("invalid_attribution_calibration_output", () => run((request) => ({ probabilities: [
      { hypothesis_id: request.hypotheses[0]!.hypothesis_id, probability_micros: 500_000 },
      { hypothesis_id: request.hypotheses[0]!.hypothesis_id, probability_micros: 500_000 },
    ] })));
    await expectCode("invalid_attribution_calibration_output", () => run((request) => ({ probabilities: [
      { hypothesis_id: request.hypotheses[0]!.hypothesis_id, probability_micros: 400_000 },
      { hypothesis_id: request.hypotheses[1]!.hypothesis_id, probability_micros: 400_000 },
    ] })));
    const getter = { probabilities: [] as unknown[] };
    Object.defineProperty(getter, "probabilities", { enumerable: true, get: () => [] });
    await expectCode("invalid_attribution_calibration_output", () => run(() => getter));
    expect(requests).toHaveLength(5);
  });

  test("provider failures expose only a closed code", async () => {
    await expectCode("attribution_calibration_failed", () => calibrateAttributionBelief({
      ...base(), evidence_factors: factors(),
    }, { calibrate: async () => { throw new Error("raw provider body and transcript"); } }));
  });
});
