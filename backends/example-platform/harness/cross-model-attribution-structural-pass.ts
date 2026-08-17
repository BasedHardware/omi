import { existsSync, mkdirSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { isProxy } from "node:util/types";

import {
  calibrateAttributionBelief,
  materializeAttributionCalibrationRequest,
  type AttributionCalibratorPort,
  type AttributionCalibrationRequest,
  type CalibrateAttributionBeliefInput,
  type CalibratedAttributionBelief,
} from "../core/consolidate/attribution-calibration";
import type { AttributionHypothesis, AttributionHypothesisKind } from "../core/consolidate/attribution-belief";
import { sha256CanonicalRedacted, type CanonicalJson } from "../core/ledger";
import { attributionCalibrationPromptCost } from "../drivers/model/glm";
import type { ModelPort } from "../drivers/model/port";
import type { ModelOperationalTelemetryEvent, ModelTelemetrySink } from "../drivers/model/telemetry";
import {
  liveModelVersion,
  MODEL_PROFILES,
  modelForProfile,
  modelPipelineResourceDigest,
} from "./model-select";
import { withOfflineModelPipelineExclusivity } from "./offline-model-pipeline-lock";

export const CROSS_MODEL_ATTRIBUTION_MANIFEST_VERSION =
  "cross-model-attribution-structural-manifest-v1" as const;
export const CROSS_MODEL_ATTRIBUTION_RESULT_VERSION =
  "cross-model-attribution-structural-result-v2" as const;
export const CROSS_MODEL_ATTRIBUTION_FAILURE_VERSION =
  "cross-model-attribution-structural-failure-v2" as const;
export const CROSS_MODEL_ATTRIBUTION_FROZEN_MANIFEST_DIGEST =
  "4d60523f51c401a66b499b73c545a64e8c3c71397564455ca5473b1467e5fcb3" as const;

const PROFILE_ORDER = ["deepseek-flash", "glm"] as const;
type Profile = typeof PROFILE_ORDER[number];
const DIGEST = /^[a-f0-9]{64}$/;
const CASE_ID = /^case-[a-z0-9-]{1,80}$/;
const MAX_CASES = 16;

export interface CrossModelStructuralManifest {
  readonly version: typeof CROSS_MODEL_ATTRIBUTION_MANIFEST_VERSION;
  readonly profiles: readonly {
    readonly profile: Profile;
    readonly model_version: string;
    readonly provider_version: string;
    readonly adapter_version: string;
    readonly resource_digest: string;
  }[];
  readonly budgets: {
    readonly max_cases_per_profile: number;
    readonly max_prompt_characters_per_case: number;
    readonly max_completion_tokens_per_call: number;
    readonly max_input_tokens_per_profile: number;
    readonly max_output_tokens_per_profile: number;
    readonly max_total_tokens_per_profile: number;
    readonly max_wall_clock_ms_per_profile: number;
  };
  readonly cases: readonly {
    readonly case_id: string;
    readonly expected_top_kind: AttributionHypothesisKind;
    readonly input: CalibrateAttributionBeliefInput;
  }[];
}

export interface CrossModelStructuralPassDependencies {
  readonly create_model: (profile: Profile, telemetry: ModelTelemetrySink, maxCompletionTokens: number) => ModelPort;
  readonly resource_digest: (profile: Profile) => string;
  readonly model_version: (profile: Profile) => string;
  readonly now_ms: () => number;
}

export interface CrossModelStructuralHypothesisDiagnostic {
  readonly hypothesis_id: string;
  readonly kind: AttributionHypothesisKind;
  readonly probability_micros: number;
}

export interface CrossModelStructuralCaseDiagnostic {
  readonly case_id: string;
  readonly code: string;
  readonly tied: boolean;
  readonly hypotheses: readonly CrossModelStructuralHypothesisDiagnostic[];
  readonly request_digest: string | null;
  readonly response_digest: string | null;
  readonly result_digest: string | null;
  readonly prompt_digest: string | null;
  readonly accounting_digest: string | null;
  readonly token_counts: Readonly<{ input: number; output: number; total: number }> | null;
}

export class CrossModelStructuralPassError extends Error {
  constructor(
    readonly code: string,
    readonly diagnostic: CrossModelStructuralCaseDiagnostic | null = null,
  ) {
    super(code);
    this.name = "CrossModelStructuralPassError";
  }
}

const fail = (
  code: string,
  diagnostic: CrossModelStructuralCaseDiagnostic | null = null,
): never => { throw new CrossModelStructuralPassError(code, diagnostic); };

const exact = (value: unknown, keys: readonly string[], code = "invalid_manifest"): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string")) fail(code);
  const sorted = (actual as string[]).sort();
  const expected = [...keys].sort();
  if (sorted.length !== expected.length || sorted.some((key, index) => key !== expected[index])) fail(code);
  for (const key of sorted) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const array = (value: unknown, maximum: number, code = "invalid_manifest"): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length === 0 || value.length > maximum) fail(code);
  const values = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(values);
  if (Reflect.ownKeys(descriptors).length !== values.length + 1) fail(code);
  return values.map((_entry: unknown, index: number) => {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    return descriptor.value;
  });
};

const positive = (value: unknown, maximum: number): number => {
  if (!Number.isSafeInteger(value) || (value as number) <= 0 || (value as number) > maximum) fail("invalid_manifest");
  return value as number;
};

const parseManifest = (value: unknown): CrossModelStructuralManifest => {
  const root = exact(value, ["version", "profiles", "budgets", "cases"]);
  if (root["version"] !== CROSS_MODEL_ATTRIBUTION_MANIFEST_VERSION) fail("invalid_manifest");
  const profiles = array(root["profiles"], 2).map((entry, index) => {
    const row = exact(entry, ["profile", "model_version", "provider_version", "adapter_version", "resource_digest"]);
    const expected = PROFILE_ORDER[index];
    if (row["profile"] !== expected
      || typeof row["model_version"] !== "string" || row["model_version"] !== MODEL_PROFILES[expected].model_id
      || row["provider_version"] !== MODEL_PROFILES[expected].provider_version
      || row["adapter_version"] !== MODEL_PROFILES[expected].adapter_version
      || typeof row["resource_digest"] !== "string" || !DIGEST.test(row["resource_digest"])) fail("invalid_manifest");
    return Object.freeze({
      profile: expected,
      model_version: row["model_version"] as string,
      provider_version: row["provider_version"] as string,
      adapter_version: row["adapter_version"] as string,
      resource_digest: row["resource_digest"] as string,
    });
  });
  if (profiles.length !== 2 || profiles[0]!.resource_digest === profiles[1]!.resource_digest) fail("invalid_manifest");

  const budget = exact(root["budgets"], [
    "max_cases_per_profile", "max_prompt_characters_per_case", "max_completion_tokens_per_call",
    "max_input_tokens_per_profile", "max_output_tokens_per_profile",
    "max_total_tokens_per_profile", "max_wall_clock_ms_per_profile",
  ]);
  const budgets = Object.freeze({
    max_cases_per_profile: positive(budget["max_cases_per_profile"], MAX_CASES),
    max_prompt_characters_per_case: positive(budget["max_prompt_characters_per_case"], 100_000),
    max_completion_tokens_per_call: positive(budget["max_completion_tokens_per_call"], 4_096),
    max_input_tokens_per_profile: positive(budget["max_input_tokens_per_profile"], 100_000),
    max_output_tokens_per_profile: positive(budget["max_output_tokens_per_profile"], 100_000),
    max_total_tokens_per_profile: positive(budget["max_total_tokens_per_profile"], 200_000),
    max_wall_clock_ms_per_profile: positive(budget["max_wall_clock_ms_per_profile"], 3_600_000),
  });
  if (budgets.max_total_tokens_per_profile
      !== budgets.max_input_tokens_per_profile + budgets.max_output_tokens_per_profile
    || budgets.max_output_tokens_per_profile
      > budgets.max_cases_per_profile * budgets.max_completion_tokens_per_call) fail("invalid_manifest");

  const seen = new Set<string>();
  const cases = array(root["cases"], MAX_CASES).map((entry) => {
    const row = exact(entry, ["case_id", "expected_top_kind", "input"]);
    if (typeof row["case_id"] !== "string") fail("invalid_manifest");
    const caseId = row["case_id"] as string;
    if (!CASE_ID.test(caseId) || seen.has(caseId)) fail("invalid_manifest");
    seen.add(caseId);
    const expectedTop = row["expected_top_kind"];
    if (expectedTop !== "owner" && expectedTop !== "entity" && expectedTop !== "source_local"
      && expectedTop !== "unknown" && expectedTop !== "true" && expectedTop !== "false") fail("invalid_manifest");
    let request;
    try { request = materializeAttributionCalibrationRequest(row["input"] as CalibrateAttributionBeliefInput); }
    catch { return fail("invalid_manifest"); }
    if (attributionCalibrationPromptCost(request) > budgets.max_prompt_characters_per_case) fail("prompt_budget_exceeded");
    return Object.freeze({
      case_id: caseId,
      expected_top_kind: expectedTop as AttributionHypothesisKind,
      input: row["input"] as CalibrateAttributionBeliefInput,
    });
  });
  if (cases.length !== budgets.max_cases_per_profile) fail("invalid_manifest");
  const manifest = Object.freeze({
    version: CROSS_MODEL_ATTRIBUTION_MANIFEST_VERSION,
    profiles: Object.freeze(profiles),
    budgets,
    cases: Object.freeze(cases),
  });
  if (sha256CanonicalRedacted(manifest as unknown as CanonicalJson)
      !== CROSS_MODEL_ATTRIBUTION_FROZEN_MANIFEST_DIGEST) fail("manifest_digest_mismatch");
  return manifest;
};

const totalUsage = (
  events: readonly ModelOperationalTelemetryEvent[],
  maxCompletionTokensPerCall: number,
) => {
  let input = 0; let output = 0; let total = 0;
  for (const event of events) {
    if (event.stage !== "provider_attempt" || event.outcome !== "success" || event.attempt !== 1
      || event.error_code !== null || event.token_counts.input <= 0 || event.token_counts.output <= 0
      || event.token_counts.output > maxCompletionTokensPerCall
      || event.token_counts.total !== event.token_counts.input + event.token_counts.output) fail("accounting_failed");
    input += event.token_counts.input; output += event.token_counts.output; total += event.token_counts.total;
  }
  return Object.freeze({ input, output, total });
};

const sameCoordinates = (
  event: ModelOperationalTelemetryEvent,
  expected: CrossModelStructuralManifest["profiles"][number],
): boolean => event.coordinates.provider_version === expected.provider_version
  && event.coordinates.adapter_version === expected.adapter_version
  && event.coordinates.model_version === expected.model_version;

const exactCoordinates = (
  left: ModelOperationalTelemetryEvent["coordinates"],
  right: ModelOperationalTelemetryEvent["coordinates"],
): boolean => JSON.stringify(left) === JSON.stringify(right);

const tokenCounts = (
  event: ModelOperationalTelemetryEvent | undefined,
): Readonly<{ input: number; output: number; total: number }> | null => {
  if (!event) return null;
  return Object.freeze({
    input: event.token_counts.input,
    output: event.token_counts.output,
    total: event.token_counts.total,
  });
};

const caseDiagnostic = (
  caseId: string,
  code: string,
  tied: boolean,
  result: CalibratedAttributionBelief | null,
  event: ModelOperationalTelemetryEvent | undefined,
): CrossModelStructuralCaseDiagnostic => {
  const counts = tokenCounts(event);
  const hypotheses = result?.belief.hypotheses ?? [];
  return Object.freeze({
    case_id: caseId,
    code,
    tied,
    hypotheses: Object.freeze(hypotheses.map((hypothesis): CrossModelStructuralHypothesisDiagnostic => Object.freeze({
      hypothesis_id: hypothesis.hypothesis_id,
      kind: hypothesis.kind,
      probability_micros: hypothesis.probability_micros,
    }))),
    request_digest: result?.receipt.request_digest ?? null,
    response_digest: result?.receipt.response_digest ?? null,
    result_digest: result?.receipt.result_digest ?? null,
    prompt_digest: event?.prompt_digest ?? null,
    accounting_digest: counts === null ? null : sha256CanonicalRedacted(counts),
    token_counts: counts,
  });
};

const usageOrNull = (
  events: readonly ModelOperationalTelemetryEvent[],
  maxCompletionTokensPerCall: number,
) => {
  try { return totalUsage(events, maxCompletionTokensPerCall); }
  catch { return null; }
};

type ProfileOutcome = {
  readonly profile: Profile;
  readonly status: "passed" | "failed";
  readonly code: string | null;
  readonly provider_calls_attempted: number;
  readonly completed_cases: number;
  readonly usage: Readonly<{ input: number; output: number; total: number }> | null;
  readonly wall_clock_ms: number | null;
  readonly failing_case: CrossModelStructuralCaseDiagnostic | null;
  readonly result: Readonly<Record<string, unknown>> | null;
};

const profileFailure = (
  profile: Profile,
  code: string,
  providerCallsAttempted: number,
  completedCases: number,
  events: readonly ModelOperationalTelemetryEvent[],
  maxCompletionTokensPerCall: number,
  started: number | null,
  nowMs: number,
  diagnostic: CrossModelStructuralCaseDiagnostic | null,
): ProfileOutcome => Object.freeze({
  profile,
  status: "failed" as const,
  code,
  provider_calls_attempted: providerCallsAttempted,
  completed_cases: completedCases,
  usage: usageOrNull(events, maxCompletionTokensPerCall),
  wall_clock_ms: started === null ? null : nowMs - started,
  failing_case: diagnostic,
  result: null,
});

const productionDependencies: CrossModelStructuralPassDependencies = Object.freeze({
  create_model: (profile: Profile, telemetry: ModelTelemetrySink, maxCompletionTokens: number) => withOfflineModelPipelineExclusivity(
    modelForProfile(profile, { telemetrySink: telemetry, maxCompletionTokens }),
    modelPipelineResourceDigest(["--model", profile]),
  ),
  resource_digest: (profile: Profile) => modelPipelineResourceDigest(["--model", profile]),
  model_version: (profile: Profile) => liveModelVersion(["--model", profile]),
  now_ms: () => Date.now(),
});

export const validateCrossModelAttributionStructuralManifest = (
  rawManifest: unknown,
): Readonly<Record<string, unknown>> => {
  const manifest = parseManifest(rawManifest);
  return Object.freeze({
    status: "valid",
    version: manifest.version,
    manifest_digest: sha256CanonicalRedacted(manifest as unknown as CanonicalJson),
    profiles: Object.freeze(manifest.profiles.map((profile) => profile.profile)),
    cases_per_profile: manifest.cases.length,
    maximum_provider_calls: manifest.cases.length * manifest.profiles.length,
  });
};

export const runCrossModelAttributionStructuralPass = async (
  rawManifest: unknown,
  outputDirectory: string,
  dependencies: CrossModelStructuralPassDependencies = productionDependencies,
): Promise<Readonly<Record<string, unknown>>> => {
  const manifest = parseManifest(rawManifest);
  const output = resolve(outputDirectory);
  if (!isAbsolute(outputDirectory) || existsSync(output)) fail("invalid_output_directory");
  mkdirSync(output, { recursive: false });
  const manifestDigest = sha256CanonicalRedacted(manifest as unknown as CanonicalJson);

  const runProfile = async (
    profileConfig: CrossModelStructuralManifest["profiles"][number],
  ): Promise<ProfileOutcome> => {
    let providerCallsAttempted = 0;
    let completedCases = 0;
    const events: ModelOperationalTelemetryEvent[] = [];
    let started: number | null = null;
    try {
      if (dependencies.resource_digest(profileConfig.profile) !== profileConfig.resource_digest
        || dependencies.model_version(profileConfig.profile) !== profileConfig.model_version) {
        fail("profile_coordinate_mismatch");
      }
      const model = dependencies.create_model(
        profileConfig.profile,
        (event: ModelOperationalTelemetryEvent) => { events.push(event); },
        manifest.budgets.max_completion_tokens_per_call,
      );
      started = dependencies.now_ms();
      const startedMs = started;
      const signal = AbortSignal.timeout(manifest.budgets.max_wall_clock_ms_per_profile);
      const cases: Record<string, unknown>[] = [];
      let baselineCoordinates: ModelOperationalTelemetryEvent["coordinates"] | null = null;
      for (const structuralCase of manifest.cases) {
        if (sha256CanonicalRedacted(manifest as unknown as CanonicalJson) !== manifestDigest) {
          fail("manifest_digest_mismatch");
        }
        const eventCount = events.length;
        const calibrator: AttributionCalibratorPort = Object.freeze({
          calibrate: (request: AttributionCalibrationRequest, lossSignal?: AbortSignal) => {
            providerCallsAttempted += 1;
            return model.invoke({
              strategy: "attribution-calibration", version: "v1", input: request,
              ...(lossSignal ? { signal: lossSignal } : {}),
            });
          },
        });
        let result: CalibratedAttributionBelief | null = null;
        try { result = await calibrateAttributionBelief(structuralCase.input, calibrator, signal); }
        catch {
          fail(
            "provider_or_contract_failure",
            caseDiagnostic(
              structuralCase.case_id, "provider_or_contract_failure", false, null, events[eventCount],
            ),
          );
        }
        const newEvents = events.slice(eventCount);
        const diagnosticFor = (code: string, tied: boolean) => caseDiagnostic(
          structuralCase.case_id, code, tied, result, newEvents[0],
        );
        if (newEvents.length !== 1) fail("accounting_failed", diagnosticFor("accounting_failed", false));
        if (!sameCoordinates(newEvents[0]!, profileConfig)) {
          fail("profile_coordinate_mismatch", diagnosticFor("profile_coordinate_mismatch", false));
        }
        if (baselineCoordinates === null) baselineCoordinates = newEvents[0]!.coordinates;
        else if (!exactCoordinates(newEvents[0]!.coordinates, baselineCoordinates)) {
          fail("profile_coordinate_mismatch", diagnosticFor("profile_coordinate_mismatch", false));
        }
        const currentUsage = (() => {
          try { return totalUsage(events, manifest.budgets.max_completion_tokens_per_call); }
          catch { return fail("accounting_failed", diagnosticFor("accounting_failed", false)); }
        })();
        if (currentUsage.input > manifest.budgets.max_input_tokens_per_profile
          || currentUsage.output > manifest.budgets.max_output_tokens_per_profile
          || currentUsage.total > manifest.budgets.max_total_tokens_per_profile) {
          fail("token_budget_exceeded", diagnosticFor("token_budget_exceeded", false));
        }
        const currentWallClock = dependencies.now_ms() - startedMs;
        if (currentWallClock < 0
          || currentWallClock > manifest.budgets.max_wall_clock_ms_per_profile) {
          fail("wall_clock_budget_exceeded", diagnosticFor("wall_clock_budget_exceeded", false));
        }
        if (result === null) fail("provider_or_contract_failure", diagnosticFor("provider_or_contract_failure", false));
        const owner = result.belief.hypotheses.find((hypothesis: AttributionHypothesis) => hypothesis.kind === "owner");
        const unknown = result.belief.hypotheses.find((hypothesis: AttributionHypothesis) => hypothesis.kind === "unknown");
        if (!owner || !unknown) {
          fail("structural_expectation_failed", diagnosticFor("structural_expectation_failed", false));
        }
        const tied = owner.probability_micros === unknown.probability_micros;
        const expectedKind = structuralCase.expected_top_kind;
        const expected = expectedKind === "owner" ? owner : expectedKind === "unknown" ? unknown : null;
        if (!expected) {
          fail("structural_expectation_failed", diagnosticFor("structural_expectation_failed", tied));
        }
        const other = expectedKind === "owner" ? unknown : owner;
        if (expected.probability_micros < other.probability_micros) {
          fail("structural_inversion", diagnosticFor("structural_inversion", tied));
        }
        const counts = tokenCounts(newEvents[0]);
        cases.push(Object.freeze({
          case_id: structuralCase.case_id,
          tied,
          hypotheses: Object.freeze(result.belief.hypotheses.map((hypothesis: AttributionHypothesis) => Object.freeze({
            hypothesis_id: hypothesis.hypothesis_id,
            kind: hypothesis.kind,
            probability_micros: hypothesis.probability_micros,
          }))),
          request_digest: result.receipt.request_digest,
          response_digest: result.receipt.response_digest,
          result_digest: result.receipt.result_digest,
          prompt_digest: newEvents[0]!.prompt_digest,
          accounting_digest: counts === null ? null : sha256CanonicalRedacted(counts),
          token_counts: counts,
          top_kind: expected.kind,
          top_probability_micros: expected.probability_micros,
        }));
        completedCases += 1;
      }
      const ownerMicrosFor = (caseId: string): number => {
        const entry = cases.find((item) => item.case_id === caseId) as
          { hypotheses?: readonly { kind: string; probability_micros: number }[] } | undefined;
        const hypotheses = entry?.hypotheses;
        if (!Array.isArray(hypotheses)) {
          fail("directional_mass_failed", caseDiagnostic(caseId, "directional_mass_failed", false, null, undefined));
        }
        const ownerHypothesis = hypotheses.find((item) => item.kind === "owner");
        if (ownerHypothesis === undefined) {
          fail("directional_mass_failed", caseDiagnostic(caseId, "directional_mass_failed", false, null, undefined));
        }
        return ownerHypothesis.probability_micros;
      };
      if (ownerMicrosFor("case-owner-support") <= ownerMicrosFor("case-owner-counter")) {
        const support = cases.find((item) => item.case_id === "case-owner-support");
        fail(
          "directional_mass_failed",
          caseDiagnostic(
            "case-owner-support",
            "directional_mass_failed",
            support?.tied === true,
            null,
            events[0],
          ),
        );
      }
      const usage = totalUsage(events, manifest.budgets.max_completion_tokens_per_call);
      if (usage.input > manifest.budgets.max_input_tokens_per_profile
        || usage.output > manifest.budgets.max_output_tokens_per_profile
        || usage.total > manifest.budgets.max_total_tokens_per_profile) fail("token_budget_exceeded");
      const wallClockMs = dependencies.now_ms() - startedMs;
      if (wallClockMs < 0 || wallClockMs > manifest.budgets.max_wall_clock_ms_per_profile) {
        fail("wall_clock_budget_exceeded");
      }
      const coordinates = events[0]!.coordinates;
      const profileResult = Object.freeze({
        version: CROSS_MODEL_ATTRIBUTION_RESULT_VERSION,
        manifest_digest: manifestDigest,
        profile: profileConfig.profile,
        resource_digest: profileConfig.resource_digest,
        coordinates,
        usage,
        wall_clock_ms: wallClockMs,
        cases: Object.freeze(cases),
      });
      await Bun.write(`${output}/${profileConfig.profile}.json`, `${JSON.stringify(profileResult, null, 2)}\n`);
      return Object.freeze({
        profile: profileConfig.profile,
        status: "passed" as const,
        code: null,
        provider_calls_attempted: providerCallsAttempted,
        completed_cases: completedCases,
        usage,
        wall_clock_ms: wallClockMs,
        failing_case: null,
        result: profileResult,
      });
    } catch (error) {
      const diagnostic = error instanceof CrossModelStructuralPassError ? error.diagnostic : null;
      const code = error instanceof CrossModelStructuralPassError ? error.code : "structural_pass_failed";
      return profileFailure(
        profileConfig.profile, code, providerCallsAttempted, completedCases, events,
        manifest.budgets.max_completion_tokens_per_call, started, dependencies.now_ms(), diagnostic,
      );
    }
  };

  const writeFailure = async (
    code: string,
    outcomes: readonly ProfileOutcome[],
  ): Promise<void> => {
    const ordered = PROFILE_ORDER.map((profile) => {
      const outcome = outcomes.find((entry) => entry.profile === profile);
      return outcome ?? profileFailure(
        profile, "structural_pass_failed", 0, 0, [], manifest.budgets.max_completion_tokens_per_call,
        null, dependencies.now_ms(), null,
      );
    });
    const failure = Object.freeze({
      version: CROSS_MODEL_ATTRIBUTION_FAILURE_VERSION,
      status: "failed",
      execution: "parallel",
      code,
      manifest_digest: manifestDigest,
      provider_calls_attempted: ordered.reduce((sum, outcome) => sum + outcome.provider_calls_attempted, 0),
      completed_cases: Object.freeze(ordered.map((outcome) => Object.freeze({
        profile: outcome.profile,
        count: outcome.completed_cases,
      }))),
      profiles: Object.freeze(ordered.map((outcome) => Object.freeze({
        profile: outcome.profile,
        status: outcome.status,
        code: outcome.code,
        provider_calls_attempted: outcome.provider_calls_attempted,
        completed_cases: outcome.completed_cases,
        usage: outcome.usage,
        wall_clock_ms: outcome.wall_clock_ms,
        failing_case: outcome.failing_case,
      }))),
    });
    await Bun.write(`${output}/failure.json`, `${JSON.stringify(failure, null, 2)}\n`).catch(() => undefined);
  };

  let outcomes: readonly ProfileOutcome[] = [];
  try {
    outcomes = await Promise.all(manifest.profiles.map((profileConfig) => runProfile(profileConfig)));
    const ordered = PROFILE_ORDER.map((profile) => outcomes.find((entry) => entry.profile === profile)!);
    const failed = ordered.filter((outcome) => outcome.status === "failed");
    const passedResults = ordered.flatMap((outcome) => outcome.result ? [outcome.result] : []);
    if (failed.length === 0 && passedResults.length === 2) {
      const signatures = passedResults.map((result) =>
        (result["cases"] as readonly Record<string, unknown>[]).map((entry) => entry["top_kind"]));
      if (JSON.stringify(signatures[0]) !== JSON.stringify(signatures[1])) {
        await writeFailure("cross_model_structural_disagreement", ordered);
        fail("cross_model_structural_disagreement");
      }
      const summary = Object.freeze({
        version: CROSS_MODEL_ATTRIBUTION_RESULT_VERSION,
        status: "passed",
        execution: "parallel",
        manifest_digest: manifestDigest,
        profiles: Object.freeze(passedResults.map((result) => Object.freeze({
          profile: result["profile"], resource_digest: result["resource_digest"],
          artifact_digest: sha256CanonicalRedacted(result as CanonicalJson),
        }))),
        structural_signature: Object.freeze(signatures[0]!),
      });
      await Bun.write(`${output}/summary.json`, `${JSON.stringify(summary, null, 2)}\n`);
      return summary;
    }
    const overallCode = failed[0]?.code ?? "structural_pass_failed";
    await writeFailure(overallCode, ordered);
    fail(overallCode);
  } catch (error) {
    const code = error instanceof CrossModelStructuralPassError ? error.code : "structural_pass_failed";
    if (!existsSync(`${output}/failure.json`)) await writeFailure(code, outcomes);
    throw error;
  }
  return fail("structural_pass_failed");
};

const argument = (name: string): string | undefined => {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
};

if (import.meta.main) {
  const manifestPath = argument("--manifest");
  const outputDirectory = argument("--output-dir");
  const validateOnly = process.argv.includes("--validate-only");
  if (!manifestPath || (!validateOnly && !outputDirectory)) {
    console.error("usage: bun run harness/cross-model-attribution-structural-pass.ts --manifest <json> (--validate-only | --output-dir <new-absolute-directory>)");
    process.exit(2);
  }
  try {
    const manifest = JSON.parse(await Bun.file(manifestPath).text()) as unknown;
    const result = validateOnly
      ? validateCrossModelAttributionStructuralManifest(manifest)
      : await runCrossModelAttributionStructuralPass(manifest, outputDirectory!);
    console.log(JSON.stringify(result));
  } catch (error) {
    const code = error instanceof CrossModelStructuralPassError ? error.code : "structural_pass_failed";
    if (outputDirectory && isAbsolute(outputDirectory) && existsSync(resolve(outputDirectory))
      && !existsSync(`${resolve(outputDirectory)}/failure.json`)) {
      await Bun.write(`${resolve(outputDirectory)}/failure.json`, `${JSON.stringify({ status: "failed", code })}\n`)
        .catch(() => undefined);
    }
    console.error(JSON.stringify({ status: "failed", code }));
    process.exit(1);
  }
}
