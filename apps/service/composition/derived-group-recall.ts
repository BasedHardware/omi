import { isProxy } from "node:util/types";

import {
  MEMORY_RECALL_KERNEL_VERSION,
  parseMemoryRecallKernelRequest,
  type MemoryRecallKernelRequest,
  type MemoryRecallKernelResponse,
} from "../../../core/retrieve/memory-recall-kernel";
import {
  buildDerivedGroupRecallCandidates,
  derivedGroupRecallInputFrontierDigest,
  derivedGroupRecallProjectedContentDigest,
  parseDerivedGroupRecallMembers,
  type DerivedGroupRecallCandidate,
  type DerivedGroupRecallMember,
} from "../../../core/retrieve/derived-group-recall-source";
import {
  identityExpressionLabelsForBeliefs,
  type IdentityExpressionAssignment,
} from "../../../core/retrieve/identity-expression-label";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertMemoryRecallKernel,
  type MemoryRecallKernel,
  type MemoryRecallKernelOutcome,
  type MemoryRecallKernelRunRequest,
} from "./memory-recall-kernel";

const PORT: unique symbol = Symbol("derived-group-recall");

export interface DerivedGroupRecallRequest {
  readonly question_text: string;
  readonly authorization_state_digest: string;
  readonly reader_projection_digest: string;
  readonly members: readonly DerivedGroupRecallMember[];
  readonly people_cluster_beliefs: readonly unknown[];
  readonly producer_request: MemoryRecallKernelRunRequest["producer_request"];
}

export type DerivedGroupRecallOutcome =
  | Readonly<{
      kind: "completed";
      response: Readonly<MemoryRecallKernelResponse>;
      candidates: readonly DerivedGroupRecallCandidate[];
      identity_expression_labels: readonly IdentityExpressionAssignment[];
      model_calls: 0 | 1;
    }>
  | Readonly<{ kind: "stopped"; stop_code: string; model_calls: 0 | 1 }>;

export interface DerivedGroupRecall {
  readonly [PORT]: true;
  answer(
    context: AuthorizedLedgerWriteContext,
    request: DerivedGroupRecallRequest,
  ): Promise<DerivedGroupRecallOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`derived group recall ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_request");
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail("invalid_request");
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_request");
  }
  return value as Record<string, unknown>;
};

export const derivedGroupRecallKernelRequest = (
  requestValue: unknown,
): Readonly<MemoryRecallKernelRequest> => {
  const input = exactRecord(requestValue, [
    "question_text", "authorization_state_digest", "reader_projection_digest", "members",
  ]);
  const members = parseDerivedGroupRecallMembers(input["members"]);
  return parseMemoryRecallKernelRequest({
    version: MEMORY_RECALL_KERNEL_VERSION,
    question_text: input["question_text"],
    authorization_state_digest: input["authorization_state_digest"],
    reader_projection_digest: input["reader_projection_digest"],
    projected_content_digest: derivedGroupRecallProjectedContentDigest(members),
    input_frontier_digest: derivedGroupRecallInputFrontierDigest(members),
  });
};

export const composeDerivedGroupRecall = (
  kernelValue: MemoryRecallKernel,
): DerivedGroupRecall => {
  const kernel = assertMemoryRecallKernel(kernelValue);
  return Object.freeze({
    [PORT]: true as const,
    async answer(
      contextValue: AuthorizedLedgerWriteContext,
      requestValue: DerivedGroupRecallRequest,
    ) {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      const request = exactRecord(requestValue, [
        "question_text", "authorization_state_digest", "reader_projection_digest",
        "members", "people_cluster_beliefs", "producer_request",
      ]);
      const members = parseDerivedGroupRecallMembers(request["members"]);
      const candidates = buildDerivedGroupRecallCandidates(members);
      const kernelRequest = derivedGroupRecallKernelRequest({
        question_text: request["question_text"],
        authorization_state_digest: request["authorization_state_digest"],
        reader_projection_digest: request["reader_projection_digest"],
        members,
      });
      const labels = identityExpressionLabelsForBeliefs(request["people_cluster_beliefs"]);
      const outcome: MemoryRecallKernelOutcome = await kernel.answer(context, {
        kernel_request: kernelRequest,
        producer_request: request["producer_request"] as MemoryRecallKernelRunRequest["producer_request"],
      });
      if (outcome.kind === "stopped") {
        return Object.freeze({
          kind: "stopped" as const,
          stop_code: outcome.stop_code,
          model_calls: outcome.model_calls,
        });
      }
      return Object.freeze({
        kind: "completed" as const,
        response: outcome.response,
        candidates,
        identity_expression_labels: labels,
        model_calls: outcome.model_calls,
      });
    },
  });
};

export const derivedGroupRecallCandidateDigest = (
  candidates: readonly DerivedGroupRecallCandidate[],
): string => sha256CanonicalContent({
  contract_version: "derived-group-recall-candidates-v1",
  candidates: candidates.map((item) => Object.freeze({
    trace_ref: item.trace_ref,
    group_projection_id: item.group_projection_id,
  })),
});
