import type { ModelPort } from "./port";
import { buildMentionRequest, planLocalHandles, type MentionModelResponse, type SourceMention } from "../../core/resolve/mentions";

/** Imperative shell: this is the only layer that invokes a model port. */
export const invokeMentionStrategy = async (port: ModelPort, mentions: readonly SourceMention[]) => {
  const request = buildMentionRequest(mentions);
  const response = await port.invoke({ strategy: request.strategy, version: request.version, input: request }) as MentionModelResponse;
  return planLocalHandles(request, response);
};
