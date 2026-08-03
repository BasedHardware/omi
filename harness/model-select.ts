import { GlmModel } from "../drivers/model/glm";
import { DeterministicFakeModel, type ModelPort } from "../drivers/model/port";

export interface ModelSelection { model: ModelPort; live: boolean; }

const liveRequested = (options: readonly string[]): boolean => options[options.indexOf("--model") + 1] === "glm";

const liveModel = (): GlmModel => {
  if (!(process.env.GLM_API_KEY ?? process.env.ZAI_API_KEY ?? process.env.OMI_BENCH_OPENAI_API_KEY)) {
    throw new Error("--model glm requires GLM_API_KEY, ZAI_API_KEY or OMI_BENCH_OPENAI_API_KEY");
  }
  return new GlmModel();
};

/** Tests and ordinary fixture runs stay entirely local. */
export const selectModel = (options: readonly string[], hermeticSeed: unknown): ModelSelection =>
  liveRequested(options) ? { model: liveModel(), live: true } : { model: new DeterministicFakeModel(hermeticSeed), live: false };

export const selectDreamModel = (options: readonly string[], hermetic: ModelPort): ModelSelection =>
  liveRequested(options) ? { model: liveModel(), live: true } : { model: hermetic, live: false };
