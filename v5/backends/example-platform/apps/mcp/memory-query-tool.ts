import { isProxy } from "node:util/types";

import {
  MEMORY_RECALL_KERNEL_VERSION,
  parseMemoryRecallKernelResponse,
  type MemoryRecallKernelResponse,
} from "../../core/retrieve/memory-recall-kernel";
import type { IdentityExpressionAssignment } from "../../core/retrieve/identity-expression-label";
import type { DerivedGroupRecall, DerivedGroupRecallOutcome } from
  "../service/composition/derived-group-recall";
import type { AuthorizedLedgerWriteContext } from "../service/auth/authorized-context";

export const MEMORY_QUERY_TOOL_NAME = "query_memory" as const;
export const MEMORY_QUERY_TOOL_VERSION = "memory-query-tool-v1" as const;
export const MEMORY_QUERY_TOOL_SCOPE = "memories.read" as const;

export interface MemoryQueryToolDependencies {
  readonly recall: DerivedGroupRecall;
  readonly authorize: (
    credential: unknown,
  ) => Promise<AuthorizedLedgerWriteContext | null>;
  readonly build_request: (
    context: AuthorizedLedgerWriteContext,
    questionText: string,
  ) => Promise<Parameters<DerivedGroupRecall["answer"]>[1] | null>;
}

export interface MemoryQueryToolResult {
  readonly version: typeof MEMORY_QUERY_TOOL_VERSION;
  readonly kernel_version: typeof MEMORY_RECALL_KERNEL_VERSION;
  readonly response: Readonly<MemoryRecallKernelResponse>;
  readonly identity_expression_labels: readonly IdentityExpressionAssignment[];
}

const fail = (code: string): never => { throw new TypeError(`memory query tool ${code}`); };

const exactDependencies = (value: unknown): MemoryQueryToolDependencies => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_dependencies");
  const keys = Reflect.ownKeys(value as object);
  const expected = ["recall", "authorize", "build_request"];
  if (keys.length !== expected.length || !expected.every((key) => keys.includes(key))) {
    fail("invalid_dependencies");
  }
  return value as MemoryQueryToolDependencies;
};

/**
 * Dark MCP query tool over the same derived-group recall kernel and grants.
 * Not registered by `createMcpProtocolHandler`.
 */
export const defineMemoryQueryTool = (
  depsValue: MemoryQueryToolDependencies,
): {
  readonly name: typeof MEMORY_QUERY_TOOL_NAME;
  readonly scope: typeof MEMORY_QUERY_TOOL_SCOPE;
  call(
    credential: unknown,
    questionText: string,
  ): Promise<
    | Readonly<{ kind: "completed"; result: MemoryQueryToolResult }>
    | Readonly<{ kind: "denied" }>
    | Readonly<{ kind: "failed" }>
  >;
} => {
  const deps = exactDependencies(depsValue);
  return Object.freeze({
    name: MEMORY_QUERY_TOOL_NAME,
    scope: MEMORY_QUERY_TOOL_SCOPE,
    async call(credential, questionText) {
      if (typeof questionText !== "string" || questionText.trim().length === 0) {
        return Object.freeze({ kind: "failed" as const });
      }
      try {
        const authorized = await deps.authorize(credential);
        if (authorized === null) return Object.freeze({ kind: "denied" as const });
        const request = await deps.build_request(authorized, questionText.trim());
        if (request === null) return Object.freeze({ kind: "denied" as const });
        const outcome: DerivedGroupRecallOutcome = await deps.recall.answer(authorized, request);
        if (outcome.kind === "stopped") return Object.freeze({ kind: "failed" as const });
        parseMemoryRecallKernelResponse(outcome.response);
        return Object.freeze({
          kind: "completed" as const,
          result: Object.freeze({
            version: MEMORY_QUERY_TOOL_VERSION,
            kernel_version: MEMORY_RECALL_KERNEL_VERSION,
            response: outcome.response,
            identity_expression_labels: outcome.identity_expression_labels,
          }),
        });
      } catch {
        return Object.freeze({ kind: "failed" as const });
      }
    },
  });
};
