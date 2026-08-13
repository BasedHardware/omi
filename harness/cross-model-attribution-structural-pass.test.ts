import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  hypothesisIdForCalibrationCandidate,
  type AttributionCalibrationRequest,
  type CalibrateAttributionBeliefInput,
} from "../core/consolidate/attribution-calibration";
import { attributionEvidenceFactorRef } from "../core/consolidate/attribution-belief";
import type { ModelPort } from "../drivers/model/port";
import type { ModelOperationalTelemetryEvent, ModelTelemetrySink } from "../drivers/model/telemetry";
import {
  CROSS_MODEL_ATTRIBUTION_FAILURE_VERSION,
  CROSS_MODEL_ATTRIBUTION_FROZEN_MANIFEST_DIGEST,
  CROSS_MODEL_ATTRIBUTION_MANIFEST_VERSION,
  CrossModelStructuralPassError,
  runCrossModelAttributionStructuralPass,
  validateCrossModelAttributionStructuralManifest,
  type CrossModelStructuralManifest,
  type CrossModelStructuralPassDependencies,
} from "./cross-model-attribution-structural-pass";

const roots: string[] = [];
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }); });

const digest = (character: string) => character.repeat(64);
const resource = {
  "deepseek-flash": "ad7b2d987e6ed6a053af240f58ebb3ba2de6a8513b58b3d2940096ea0c312634",
  glm: "5bfb7391503ec9de7fea22d69703d20657df261a13eaf506f075835e857cec6e",
} as const;

const input = (suffix: string, direction: "support" | "counter"): CalibrateAttributionBeliefInput => {
  const common = {
    owner_account_id: "account:cross-model-structural-heldout", belief_kind: "source_identity" as const,
    about_ref: `about1_${digest(suffix)}`, observation_ref: `obsref1_${digest(suffix)}`,
  };
  const owner = { kind: "owner" as const, target_ref: null };
  const unknown = { kind: "unknown" as const, target_ref: null };
  const hypothesis = hypothesisIdForCalibrationCandidate(common, owner);
  const factor = {
    evidence_ref: `atevidence1_${digest(suffix)}`,
    independence_group_ref: `atind1_${digest(suffix)}`,
    hypothesis_id: hypothesis, direction, factor_contract_digest: digest("c"),
  };
  return {
    ...common, observation_content_digest: digest("d"), graph_frontier: digest("e"),
    hypothesis_candidates: [owner, unknown],
    evidence_factors: [{ factor_ref: attributionEvidenceFactorRef(factor), ...factor }],
    attribution_contract_digest: digest("f"), aggregation_contract_digest: digest("1"),
    calibration_contract_digest: digest("2"), created_at_event_time: 1, previous_revision: null,
  };
};

const manifest = (): CrossModelStructuralManifest => ({
  version: CROSS_MODEL_ATTRIBUTION_MANIFEST_VERSION,
  profiles: [
    { profile: "deepseek-flash", model_version: "deepseek-v4-flash", provider_version: "opencode-go-openai-compatible-v1", adapter_version: "openai-compatible-json-adapter-v1", resource_digest: resource["deepseek-flash"] },
    { profile: "glm", model_version: "glm-4.7", provider_version: "openai-compatible-glm-v1", adapter_version: "glm-openai-compatible-adapter-v1", resource_digest: resource.glm },
  ],
  budgets: {
    max_cases_per_profile: 3, max_prompt_characters_per_case: 20_000,
    max_completion_tokens_per_call: 256, max_input_tokens_per_profile: 4_000,
    max_output_tokens_per_profile: 768, max_total_tokens_per_profile: 4_768,
    max_wall_clock_ms_per_profile: 300_000,
  },
  cases: [
    { case_id: "case-owner-support", expected_top_kind: "owner", input: input("3", "support") },
    { case_id: "case-owner-counter", expected_top_kind: "unknown", input: input("4", "counter") },
    { case_id: "case-independent-support", expected_top_kind: "owner", input: input("5", "support") },
  ],
});

type Mode = "valid" | "malformed" | "coordinate_drift" | "later_coordinate_drift" | "oversized_output" | "tie";
type ProfileName = "deepseek-flash" | "glm";

const event = (
  profile: ProfileName,
  promptDigest: string,
): ModelOperationalTelemetryEvent => ({
  version: "model-operational-telemetry-v1", stage: "provider_attempt", outcome: "success",
  error_code: null, prompt_digest: promptDigest,
  coordinates: {
    provider_version: profile === "glm" ? "openai-compatible-glm-v1" : "opencode-go-openai-compatible-v1",
    model_version: profile === "glm" ? "glm-4.7" : "deepseek-v4-flash",
    adapter_version: profile === "glm" ? "glm-openai-compatible-adapter-v1" : "openai-compatible-json-adapter-v1",
    strategy_version: "attribution-calibration", prompt_version: "v1",
    parser_schema_version: "attribution-calibration:v1:parser-v1", policy_version: "model-edge-policy-v1",
    retry_version: "attribution-single-attempt-v1", sampling_tool_version: "temperature-zero-thinking-disabled-json-v1",
    cache_format_version: "qa-model-verdict-cache-v2",
  },
  attempt: 1, duration_ms: 1, token_counts: { input: 100, output: 20, total: 120 },
});

const modeFor = (
  modes: Mode | Partial<Record<ProfileName, Mode>>,
  profile: ProfileName,
): Mode => (typeof modes === "string" ? modes : (modes[profile] ?? "valid"));

const dependencies = (
  modes: Mode | Partial<Record<ProfileName, Mode>> = "valid",
): CrossModelStructuralPassDependencies => ({
  create_model: (profile, telemetry: ModelTelemetrySink): ModelPort => ({
    invoke: async (request) => {
      const calibration = request.input as AttributionCalibrationRequest;
      const mode = modeFor(modes, profile);
      const telemetryEvent = event(profile, digest(profile === "glm" ? "7" : "8"));
      const laterDrift = mode === "later_coordinate_drift"
        && calibration.observation_ref.endsWith(digest("4"));
      telemetry(mode === "coordinate_drift" || laterDrift
        ? { ...telemetryEvent, coordinates: { ...telemetryEvent.coordinates, provider_version: "wrong-provider-v1" } }
        : mode === "oversized_output"
          ? { ...telemetryEvent, token_counts: { input: 100, output: 257, total: 357 } }
          : telemetryEvent);
      if (mode === "malformed") return { probabilities: [] };
      const support = calibration.evidence_groups[0]!.factors[0]!.direction === "support";
      const ownerMicros = mode === "tie" ? 500_000 : (support ? 700_000 : 300_000);
      return { probabilities: calibration.hypotheses.map((hypothesis) => ({
        hypothesis_id: hypothesis.hypothesis_id,
        probability_micros: hypothesis.kind === "owner" ? ownerMicros : 1_000_000 - ownerMicros,
      })) };
    },
    render: async () => ({ summary_text: "", citations: [] }),
    compose: async () => ({ answer_text: "", citations: [], assertions: [] }),
  }),
  resource_digest: (profile) => resource[profile],
  model_version: (profile) => profile === "glm" ? "glm-4.7" : "deepseek-v4-flash",
  now_ms: () => 1,
});

const output = () => {
  const parent = mkdtempSync(join(tmpdir(), "omi-cross-model-test-"));
  roots.push(parent);
  return join(parent, "result");
};

describe("bounded cross-model attribution structural pass", () => {
  test("runs DeepSeek and GLM in parallel under exact accounting and retains separate content-free artifacts", async () => {
    const target = output();
    const result = await runCrossModelAttributionStructuralPass(manifest(), target, dependencies());
    expect(result).toMatchObject({
      status: "passed",
      execution: "parallel",
      structural_signature: ["owner", "unknown", "owner"],
    });
    for (const profile of ["deepseek-flash", "glm"]) {
      const artifact = JSON.parse(readFileSync(join(target, `${profile}.json`), "utf8"));
      expect(artifact).toMatchObject({ profile, usage: { input: 300, output: 60, total: 360 } });
      expect(JSON.stringify(artifact)).not.toContain("account:cross-model-structural-heldout");
    }
    expect(JSON.parse(readFileSync(join(target, "summary.json"), "utf8"))).toEqual(result);
  });

  test("keeps both provider calls in flight rather than sequencing GLM after DeepSeek", async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const deps = dependencies();
    const result = await runCrossModelAttributionStructuralPass(manifest(), output(), {
      ...deps,
      create_model: (profile, telemetry, maxTokens) => {
        const model = deps.create_model(profile, telemetry, maxTokens);
        return {
          ...model,
          invoke: async (...invokeArgs) => {
            inFlight += 1;
            maxInFlight = Math.max(maxInFlight, inFlight);
            try { return await model.invoke(...invokeArgs); }
            finally { inFlight -= 1; }
          },
        };
      },
    });
    expect(result).toMatchObject({ status: "passed", execution: "parallel" });
    expect(maxInFlight).toBe(2);
  });

  test("fails before provider construction for profile/resource drift or hostile manifest shapes", async () => {
    let constructed: string[] = [];
    const deps = dependencies();
    const target = output();
    await expect(runCrossModelAttributionStructuralPass(manifest(), target, {
      ...deps,
      resource_digest: (profile) => profile === "deepseek-flash" ? digest("9") : deps.resource_digest(profile),
      create_model: (profile, telemetry, maxTokens) => {
        constructed.push(profile);
        return deps.create_model(profile, telemetry, maxTokens);
      },
    })).rejects.toMatchObject({ code: "profile_coordinate_mismatch" });
    expect(constructed).toEqual(["glm"]);
    expect(JSON.parse(readFileSync(join(target, "failure.json"), "utf8"))).toMatchObject({
      execution: "parallel",
      profiles: [
        { profile: "deepseek-flash", status: "failed", code: "profile_coordinate_mismatch", provider_calls_attempted: 0 },
        { profile: "glm", status: "passed", code: null, provider_calls_attempted: 3, completed_cases: 3 },
      ],
    });

    constructed = [];
    const getter = Object.defineProperty({}, "version", { enumerable: true, get: () => CROSS_MODEL_ATTRIBUTION_MANIFEST_VERSION });
    await expect(runCrossModelAttributionStructuralPass(getter, output(), {
      ...deps,
      create_model: (profile, telemetry, maxTokens) => {
        constructed.push(profile);
        return deps.create_model(profile, telemetry, maxTokens);
      },
    })).rejects.toBeInstanceOf(CrossModelStructuralPassError);
    expect(constructed).toEqual([]);
  });

  test("pins the exact held-out manifest and every preregistered budget", () => {
    expect(validateCrossModelAttributionStructuralManifest(manifest())).toMatchObject({
      manifest_digest: CROSS_MODEL_ATTRIBUTION_FROZEN_MANIFEST_DIGEST,
      cases_per_profile: 3,
      maximum_provider_calls: 6,
    });
    const frozen = structuredClone(manifest());
    const fewerCases = {
      ...frozen,
      budgets: { ...frozen.budgets, max_cases_per_profile: 2 },
      cases: frozen.cases.slice(0, -1),
    };
    expect(() => validateCrossModelAttributionStructuralManifest(fewerCases))
      .toThrow(CrossModelStructuralPassError);
    const raisedBudget = structuredClone(manifest());
    (raisedBudget.budgets as { max_completion_tokens_per_call: number }).max_completion_tokens_per_call = 4_096;
    (raisedBudget.budgets as { max_output_tokens_per_profile: number }).max_output_tokens_per_profile = 12_288;
    (raisedBudget.budgets as { max_total_tokens_per_profile: number }).max_total_tokens_per_profile = 16_288;
    expect(() => validateCrossModelAttributionStructuralManifest(raisedBudget))
      .toThrow(expect.objectContaining({ code: "manifest_digest_mismatch" }));
  });

  test("still attempts GLM when DeepSeek is malformed and retains a diagnostic failure receipt", async () => {
    let profiles = 0;
    const deps = dependencies({ "deepseek-flash": "malformed", glm: "valid" });
    const target = output();
    await expect(runCrossModelAttributionStructuralPass(manifest(), target, {
      ...deps, create_model: (...args) => { profiles += 1; return deps.create_model(...args); },
    })).rejects.toMatchObject({ code: "provider_or_contract_failure" });
    expect(profiles).toBe(2);
    const failure = JSON.parse(readFileSync(join(target, "failure.json"), "utf8"));
    expect(failure).toMatchObject({
      version: CROSS_MODEL_ATTRIBUTION_FAILURE_VERSION,
      status: "failed",
      execution: "parallel",
      code: "provider_or_contract_failure",
      provider_calls_attempted: 4,
      completed_cases: [
        { profile: "deepseek-flash", count: 0 },
        { profile: "glm", count: 3 },
      ],
      profiles: [
        {
          profile: "deepseek-flash",
          status: "failed",
          code: "provider_or_contract_failure",
          provider_calls_attempted: 1,
          failing_case: {
            case_id: "case-owner-support",
            code: "provider_or_contract_failure",
            tied: false,
            hypotheses: [],
          },
        },
        { profile: "glm", status: "passed", code: null, provider_calls_attempted: 3, failing_case: null },
      ],
    });
    expect(JSON.stringify(failure)).not.toContain("account:cross-model-structural-heldout");
  });

  test("stops that provider on provenance drift or a per-call completion overrun without dropping GLM", async () => {
    for (const [mode, code] of [
      ["coordinate_drift", "profile_coordinate_mismatch"],
      ["oversized_output", "accounting_failed"],
    ] as const) {
      const calls = { "deepseek-flash": 0, glm: 0 };
      const deps = dependencies({ "deepseek-flash": mode, glm: "valid" });
      const target = output();
      await expect(runCrossModelAttributionStructuralPass(manifest(), target, {
        ...deps,
        create_model: (profile, telemetry, maxTokens) => {
          const model = deps.create_model(profile, telemetry, maxTokens);
          return { ...model, invoke: async (...invokeArgs) => {
            calls[profile] += 1;
            return model.invoke(...invokeArgs);
          } };
        },
      })).rejects.toMatchObject({ code });
      expect(calls).toEqual({ "deepseek-flash": 1, glm: 3 });
      expect(JSON.parse(readFileSync(join(target, "failure.json"), "utf8"))).toMatchObject({
        status: "failed",
        execution: "parallel",
        code,
        version: CROSS_MODEL_ATTRIBUTION_FAILURE_VERSION,
        manifest_digest: CROSS_MODEL_ATTRIBUTION_FROZEN_MANIFEST_DIGEST,
        provider_calls_attempted: 4,
        completed_cases: [
          { profile: "deepseek-flash", count: 0 },
          { profile: "glm", count: 3 },
        ],
        profiles: [
          { profile: "deepseek-flash", status: "failed", code, provider_calls_attempted: 1 },
          { profile: "glm", status: "passed", code: null, provider_calls_attempted: 3 },
        ],
      });
    }
  });

  test("stops immediately when any non-provider coordinate drifts between calls on that provider", async () => {
    const calls = { "deepseek-flash": 0, glm: 0 };
    const deps = dependencies();
    const target = output();
    await expect(runCrossModelAttributionStructuralPass(manifest(), target, {
      ...deps,
      create_model: (profile, telemetry, maxTokens) => {
        const model = deps.create_model(profile, (telemetryEvent) => {
          calls[profile] += 1;
          telemetry(profile === "deepseek-flash" && calls[profile] === 2
            ? { ...telemetryEvent, coordinates: { ...telemetryEvent.coordinates, policy_version: "drifted-policy-v2" } }
            : telemetryEvent);
        }, maxTokens);
        return model;
      },
    })).rejects.toMatchObject({ code: "profile_coordinate_mismatch" });
    expect(calls).toEqual({ "deepseek-flash": 2, glm: 3 });
    expect(JSON.parse(readFileSync(join(target, "failure.json"), "utf8"))).toMatchObject({
      execution: "parallel",
      provider_calls_attempted: 5,
      completed_cases: [
        { profile: "deepseek-flash", count: 1 },
        { profile: "glm", count: 3 },
      ],
    });
  });

  test("retains hypothesis micros and tie diagnostics without dropping the failing case or weakening unique-top", async () => {
    const heldOut = manifest();
    const ownerId = hypothesisIdForCalibrationCandidate(heldOut.cases[0]!.input, { kind: "owner", target_ref: null });
    const unknownId = hypothesisIdForCalibrationCandidate(heldOut.cases[0]!.input, { kind: "unknown", target_ref: null });
    const target = output();
    await expect(runCrossModelAttributionStructuralPass(
      heldOut,
      target,
      dependencies({ "deepseek-flash": "tie", glm: "tie" }),
    )).rejects.toMatchObject({ code: "ambiguous_structural_result" });
    const failure = JSON.parse(readFileSync(join(target, "failure.json"), "utf8"));
    expect(failure).toMatchObject({
      version: CROSS_MODEL_ATTRIBUTION_FAILURE_VERSION,
      execution: "parallel",
      code: "ambiguous_structural_result",
      provider_calls_attempted: 2,
      completed_cases: [
        { profile: "deepseek-flash", count: 0 },
        { profile: "glm", count: 0 },
      ],
    });
    for (const profile of ["deepseek-flash", "glm"] as const) {
      const row = failure.profiles.find((entry: { profile: string }) => entry.profile === profile);
      expect(row).toMatchObject({
        status: "failed",
        code: "ambiguous_structural_result",
        provider_calls_attempted: 1,
        failing_case: {
          case_id: "case-owner-support",
          code: "ambiguous_structural_result",
          tied: true,
          hypotheses: [
            { hypothesis_id: ownerId, kind: "owner", probability_micros: 500_000 },
            { hypothesis_id: unknownId, kind: "unknown", probability_micros: 500_000 },
          ],
          token_counts: { input: 100, output: 20, total: 120 },
        },
      });
      expect(row.failing_case.request_digest).toMatch(/^[a-f0-9]{64}$/);
      expect(row.failing_case.response_digest).toMatch(/^[a-f0-9]{64}$/);
      expect(row.failing_case.prompt_digest).toMatch(/^[a-f0-9]{64}$/);
      expect(row.failing_case.accounting_digest).toMatch(/^[a-f0-9]{64}$/);
    }
    expect(JSON.stringify(failure)).not.toContain("account:cross-model-structural-heldout");
  });

  test("still measures GLM unique-top when DeepSeek ties on the retained support case", async () => {
    const calls = { "deepseek-flash": 0, glm: 0 };
    const deps = dependencies({ "deepseek-flash": "tie", glm: "valid" });
    const target = output();
    await expect(runCrossModelAttributionStructuralPass(manifest(), target, {
      ...deps,
      create_model: (profile, telemetry, maxTokens) => {
        const model = deps.create_model(profile, telemetry, maxTokens);
        return { ...model, invoke: async (...invokeArgs) => {
          calls[profile] += 1;
          return model.invoke(...invokeArgs);
        } };
      },
    })).rejects.toMatchObject({ code: "ambiguous_structural_result" });
    expect(calls).toEqual({ "deepseek-flash": 1, glm: 3 });
    const failure = JSON.parse(readFileSync(join(target, "failure.json"), "utf8"));
    expect(failure.profiles).toMatchObject([
      {
        profile: "deepseek-flash",
        status: "failed",
        code: "ambiguous_structural_result",
        failing_case: { case_id: "case-owner-support", tied: true },
      },
      {
        profile: "glm",
        status: "passed",
        code: null,
        provider_calls_attempted: 3,
        completed_cases: 3,
        failing_case: null,
      },
    ]);
    expect(JSON.parse(readFileSync(join(target, "glm.json"), "utf8"))).toMatchObject({
      profile: "glm",
      cases: [
        { case_id: "case-owner-support", top_kind: "owner" },
        { case_id: "case-owner-counter", top_kind: "unknown" },
        { case_id: "case-independent-support", top_kind: "owner" },
      ],
    });
  });
});
