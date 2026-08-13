import { CodexModel } from "../drivers/model/codex";
import { GlmModel } from "../drivers/model/glm";
import { DeterministicFakeModel, type ModelPort } from "../drivers/model/port";
import { CachingModelPort, SqliteVerdictStore, verdictCachePath } from "../drivers/model/verdict-cache";

export interface ModelSelection { model: ModelPort; live: boolean; }

export interface ModelProfile {
  readonly model_id: string;
  readonly base_url?: string;
  readonly api_key_env: readonly string[];
  readonly prompt_env_defaults?: Readonly<Record<string, string>>;
}

export const MODEL_PROFILES: Readonly<Record<string, ModelProfile>> = Object.freeze({
  glm: Object.freeze({
    model_id: "glm-4.7",
    api_key_env: Object.freeze(["GLM_API_KEY", "ZAI_API_KEY", "OMI_BENCH_OPENAI_API_KEY"]),
    prompt_env_defaults: Object.freeze({ OMI_BOUNDARY_VERSION: "v5" }),
  }),
  "deepseek-flash": Object.freeze({
    model_id: "deepseek-v4-flash",
    base_url: "https://opencode.ai/zen/go/v1",
    api_key_env: Object.freeze(["OPENCODE_GO_API_KEY"]),
    prompt_env_defaults: Object.freeze({ OMI_BOUNDARY_VERSION: "v5" }),
  }),
});

const requestedModel = (options: readonly string[]): string | undefined => {
  const index = options.indexOf("--model");
  if (index < 0) return undefined;
  const requested = options[index + 1];
  if (!requested || requested.startsWith("--")) throw new Error("--model requires a named profile");
  return requested;
};

const liveRequested = (options: readonly string[]): boolean => {
  const requested = requestedModel(options);
  if (requested === undefined) return false;
  if (requested === "codex" || Object.hasOwn(MODEL_PROFILES, requested)) return true;
  throw new Error(`unknown model profile: ${requested}`);
};

const resolvedModelId = (name: string, profile: ModelProfile): string =>
  name === "glm" ? process.env["OMI_BENCH_OPENAI_MODEL"] ?? profile.model_id : profile.model_id;

/** The cache key must separate models: the same prompt answered by glm-4.7 and
 * by deepseek-v4-flash or Codex are different verdicts, not one cache entry. */
export const modelProfileCacheNamespace = (options: readonly string[]): string => {
  const requested = requestedModel(options);
  if (requested === "codex") {
    return `codex:${process.env["OMI_CODEX_MODEL"] ?? "gpt-5.3-codex-spark"}:${process.env["OMI_CODEX_REASONING"] ?? "low"}`;
  }
  const name = requested ?? "glm";
  const profile = MODEL_PROFILES[name];
  if (!profile) throw new Error(`unknown model profile: ${name}`);
  return `${name}:${resolvedModelId(name, profile)}`;
};

export const profileApiKey = (profile: ModelProfile): string | undefined =>
  profile.api_key_env.map((name) => process.env[name]).find((value) => !!value);

export const modelForProfile = (name: string): GlmModel => {
  const profile = MODEL_PROFILES[name];
  if (!profile) {
    throw new Error(`unknown model profile: ${name} (known: ${Object.keys(MODEL_PROFILES).join(", ")})`);
  }
  const apiKey = profileApiKey(profile);
  if (!apiKey) throw new Error(`--model ${name} requires one of ${profile.api_key_env.join(", ")}`);
  for (const [key, value] of Object.entries(profile.prompt_env_defaults ?? {})) {
    if (process.env[key] === undefined) process.env[key] = value;
  }
  return new GlmModel({
    apiKey,
    ...(profile.base_url ? { baseUrl: profile.base_url } : {}),
    model: resolvedModelId(name, profile),
  });
};

const bare = (options: readonly string[]): ModelPort => {
  const requested = requestedModel(options);
  if (requested === "codex") return new CodexModel();
  return modelForProfile(requested ?? "glm");
};

/** Opt-in via OMI_VERDICT_CACHE=<path>; unset leaves the port exactly as before. */
const liveModel = (options: readonly string[]): ModelPort => {
  const model = bare(options);
  const path = verdictCachePath();
  return path
    ? new CachingModelPort(model, new SqliteVerdictStore(path), modelProfileCacheNamespace(options))
    : model;
};

/** Tests and ordinary fixture runs stay entirely local. */
export const selectModel = (options: readonly string[], hermeticSeed: unknown): ModelSelection =>
  liveRequested(options) ? { model: liveModel(options), live: true } : { model: new DeterministicFakeModel(hermeticSeed), live: false };

export const selectDreamModel = (options: readonly string[], hermetic: ModelPort): ModelSelection =>
  liveRequested(options) ? { model: liveModel(options), live: true } : { model: hermetic, live: false };

export const liveModelVersion = (options: readonly string[]): string => {
  const requested = requestedModel(options);
  if (requested === "codex") return process.env["OMI_CODEX_MODEL"] ?? "gpt-5.3-codex-spark";
  const name = requested ?? "glm";
  const profile = MODEL_PROFILES[name];
  if (!profile) throw new Error(`unknown model profile: ${name}`);
  return resolvedModelId(name, profile);
};
