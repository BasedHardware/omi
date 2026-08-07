import { CodexModel } from "../drivers/model/codex";
import { GlmModel } from "../drivers/model/glm";
import { DeterministicFakeModel, type ModelPort } from "../drivers/model/port";
import { CachingModelPort, SqliteVerdictStore, verdictCachePath } from "../drivers/model/verdict-cache";

export interface ModelSelection { model: ModelPort; live: boolean; }

const requestedModel = (options: readonly string[]): string | undefined => options[options.indexOf("--model") + 1];
const liveRequested = (options: readonly string[]): boolean => ["glm", "codex"].includes(requestedModel(options) ?? "");

/** The cache key must separate models: the same prompt answered by glm-4.7 and
 * by gpt-5.3-codex-spark are two different verdicts, not one cache entry. */
const namespaceFor = (options: readonly string[]): string =>
  requestedModel(options) === "codex"
    ? `codex:${process.env.OMI_CODEX_MODEL ?? "gpt-5.3-codex-spark"}:${process.env.OMI_CODEX_REASONING ?? "low"}`
    : `glm:${process.env.OMI_BENCH_OPENAI_MODEL ?? "glm-4.7"}`;

const bare = (options: readonly string[]): ModelPort => {
  if (requestedModel(options) === "codex") return new CodexModel();
  if (!(process.env.GLM_API_KEY ?? process.env.ZAI_API_KEY ?? process.env.OMI_BENCH_OPENAI_API_KEY)) {
    throw new Error("--model glm requires GLM_API_KEY, ZAI_API_KEY or OMI_BENCH_OPENAI_API_KEY");
  }
  return new GlmModel();
};

/** Opt-in via OMI_VERDICT_CACHE=<path>; unset leaves the port exactly as before. */
const liveModel = (options: readonly string[]): ModelPort => {
  const model = bare(options);
  const path = verdictCachePath();
  return path ? new CachingModelPort(model, new SqliteVerdictStore(path), namespaceFor(options)) : model;
};

/** Tests and ordinary fixture runs stay entirely local. */
export const selectModel = (options: readonly string[], hermeticSeed: unknown): ModelSelection =>
  liveRequested(options) ? { model: liveModel(options), live: true } : { model: new DeterministicFakeModel(hermeticSeed), live: false };

export const selectDreamModel = (options: readonly string[], hermetic: ModelPort): ModelSelection =>
  liveRequested(options) ? { model: liveModel(options), live: true } : { model: hermetic, live: false };
