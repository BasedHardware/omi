import { CodexModel } from "../drivers/model/codex";
import { GlmModel } from "../drivers/model/glm";
import { DeterministicFakeModel, type ModelPort } from "../drivers/model/port";

export interface ModelSelection { model: ModelPort; live: boolean; }

const requestedModel = (options: readonly string[]): string | undefined => options[options.indexOf("--model") + 1];
const liveRequested = (options: readonly string[]): boolean => ["glm", "codex"].includes(requestedModel(options) ?? "");

const liveModel = (options: readonly string[]): ModelPort => {
  if (requestedModel(options) === "codex") return new CodexModel();
  if (!(process.env.GLM_API_KEY ?? process.env.ZAI_API_KEY ?? process.env.OMI_BENCH_OPENAI_API_KEY)) {
    throw new Error("--model glm requires GLM_API_KEY, ZAI_API_KEY or OMI_BENCH_OPENAI_API_KEY");
  }
  return new GlmModel();
};

/** Tests and ordinary fixture runs stay entirely local. */
export const selectModel = (options: readonly string[], hermeticSeed: unknown): ModelSelection =>
  liveRequested(options) ? { model: liveModel(options), live: true } : { model: new DeterministicFakeModel(hermeticSeed), live: false };

export const selectDreamModel = (options: readonly string[], hermetic: ModelPort): ModelSelection =>
  liveRequested(options) ? { model: liveModel(options), live: true } : { model: hermetic, live: false };
