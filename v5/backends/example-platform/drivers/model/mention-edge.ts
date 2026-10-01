import type { ModelPort } from "./port";
import { buildMentionRequest, planLocalHandles, type MentionModelResponse, type SourceMention } from "../../core/resolve/mentions";
import { buildMentionDetectionRequest, planMentionDetection, type MentionDetectionResponse } from "../../core/resolve/mention-detection";
import type { Evidence, ProvisionalClaim } from "../../core/schema";

/** Imperative shell: this is the only layer that invokes a model port. */
export const invokeMentionStrategy = async (port: ModelPort, mentions: readonly SourceMention[]) => {
  const request = buildMentionRequest(mentions);
  const response = await port.invoke({ strategy: request.strategy, version: request.version, input: request }) as MentionModelResponse;
  return planLocalHandles(request, response);
};

/** Claim-role mention edge. It persists a source-local mention before durable entity resolution. */
export const invokeClaimMentionStrategy = async (port: ModelPort, owner_account_id: string, claims: readonly ProvisionalClaim[], evidence: readonly Evidence[]) => {
  const request = buildMentionDetectionRequest(claims, evidence);
  const response = await port.invoke({ strategy: request.strategy, version: request.version, input: request }) as MentionDetectionResponse;
  return planMentionDetection(owner_account_id, request, response);
};
