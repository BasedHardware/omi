import { isProxy } from "node:util/types";

import {
  buildMemoryRecallKernelResponse,
  MEMORY_RECALL_KERNEL_VERSION,
  parseMemoryRecallKernelRequest,
  type MemoryRecallKernelRequest,
  type MemoryRecallKernelResponse,
} from "../../../core/retrieve/memory-recall-kernel";
import type { RecallCompletenessInput } from "../../../core/retrieve/recall-integrity";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertMemoryAuthorizedQueryGroundingProducer,
  type AuthorizedQueryGroundingProducerOutcome,
  type AuthorizedQueryGroundingProducerRequest,
  type MemoryAuthorizedQueryGroundingProducer,
} from "../workers/memory-authorized-query-grounding-producer";
import { parseMemoryReadEvaluationResult } from "../workers/memory-read-evaluation-result";

const PORT: unique symbol = Symbol("memory-recall-kernel");

export interface MemoryRecallKernelDependencies {
  readonly producer: MemoryAuthorizedQueryGroundingProducer;
  readonly completeness_for: (
    request: Readonly<MemoryRecallKernelRequest>,
  ) => RecallCompletenessInput;
}

export interface MemoryRecallKernelRunRequest {
  readonly kernel_request: MemoryRecallKernelRequest;
  readonly producer_request: AuthorizedQueryGroundingProducerRequest;
}

export type MemoryRecallKernelOutcome =
  | Readonly<{ kind: "completed"; response: Readonly<MemoryRecallKernelResponse>; model_calls: 0 | 1 }>
  | Readonly<{ kind: "stopped"; stop_code: string; model_calls: 0 | 1 }>;

export interface MemoryRecallKernel {
  readonly [PORT]: true;
  answer(
    context: AuthorizedLedgerWriteContext,
    request: MemoryRecallKernelRunRequest,
  ): Promise<MemoryRecallKernelOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`memory recall kernel composition ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_config");
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail("invalid_config");
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_config");
  }
  return value as Record<string, unknown>;
};

export const composeMemoryRecallKernel = (
  configValue: MemoryRecallKernelDependencies,
): MemoryRecallKernel => {
  const config = exactRecord(configValue, ["producer", "completeness_for"]);
  const producer = assertMemoryAuthorizedQueryGroundingProducer(config["producer"]);
  const completenessFor = config["completeness_for"] as MemoryRecallKernelDependencies["completeness_for"];
  if (typeof completenessFor !== "function" || isProxy(completenessFor)) fail("invalid_config");
  return Object.freeze({
    [PORT]: true as const,
    async answer(contextValue, requestValue) {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      const request = exactRecord(requestValue, ["kernel_request", "producer_request"]);
      const kernelRequest = parseMemoryRecallKernelRequest(request["kernel_request"]);
      const producerOutcome = await producer.run(
        context,
        request["producer_request"] as AuthorizedQueryGroundingProducerRequest,
      );
      if (producerOutcome.kind === "stopped") {
        return Object.freeze({
          kind: "stopped" as const,
          stop_code: producerOutcome.stop_code,
          model_calls: producerOutcome.model_calls,
        });
      }
      const evaluation = parseMemoryReadEvaluationResult(producerOutcome.result.normalized_result);
      const response = buildMemoryRecallKernelResponse({
        request: kernelRequest,
        answer_text: evaluation.answer_text,
        absence: evaluation.absence,
        assertions: evaluation.assertions.map((assertion) => Object.freeze({
          ordinal: assertion.ordinal,
          text: assertion.text,
          citations: assertion.citations,
        })),
        completeness_input: completenessFor(kernelRequest),
      });
      if (response.question_digest !== memoryRecallKernelQuestionDigest(kernelRequest.question_text)) {
        fail("question_digest_mismatch");
      }
      return Object.freeze({
        kind: "completed" as const,
        response,
        model_calls: producerOutcome.model_calls,
      });
    },
  });
};

const memoryRecallKernelQuestionDigest = (questionText: string): string =>
  sha256CanonicalContent({
    contract_version: MEMORY_RECALL_KERNEL_VERSION,
    question_text: questionText,
  });
