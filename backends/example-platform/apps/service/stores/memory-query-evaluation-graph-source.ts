import { isProxy } from "node:util/types";

import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type { MemoryEvaluationEvidenceSourceRequest } from "./memory-evaluation-evidence-source";

const PORT: unique symbol = Symbol("memory-query-evaluation-graph-source");
const CAPABILITY = "memories.experiments.shadow";
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const sources = new WeakSet<object>();

export interface MemoryQueryEvaluationGraphSource {
  readonly [PORT]: true;
  load(
    context: AuthorizedLedgerWriteContext,
    request: MemoryEvaluationEvidenceSourceRequest,
  ): Promise<unknown>;
}

export type MemoryQueryEvaluationGraphSourceImplementation = (
  context: AuthorizedLedgerWriteContext,
  request: MemoryEvaluationEvidenceSourceRequest,
) => Promise<unknown>;

const fail = (code: string): never => {
  throw new TypeError(`memory query evaluation graph source ${code}`);
};

const exactRequest = (value: unknown): Readonly<MemoryEvaluationEvidenceSourceRequest> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_request");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  const expected = ["input_frontier", "source_kind", "source_ref"];
  if (keys.some((key) => typeof key !== "string") || keys.length !== expected.length
    || (keys as string[]).sort().some((key, index) => key !== expected[index])) fail("invalid_request");
  for (const key of expected) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("invalid_request");
  }
  if (descriptors.source_kind!.value !== "authorized_graph_snapshot"
    || typeof descriptors.source_ref!.value !== "string"
    || !TOKEN.test(descriptors.source_ref!.value)
    || typeof descriptors.input_frontier!.value !== "string"
    || !TOKEN.test(descriptors.input_frontier!.value)) fail("invalid_request");
  return Object.freeze({
    source_kind: "authorized_graph_snapshot" as const,
    source_ref: descriptors.source_ref!.value as string,
    input_frontier: descriptors.input_frontier!.value as string,
  });
};

export const defineMemoryQueryEvaluationGraphSource = (
  implementationValue: MemoryQueryEvaluationGraphSourceImplementation,
): MemoryQueryEvaluationGraphSource => {
  if (typeof implementationValue !== "function" || isProxy(implementationValue)) {
    fail("invalid_implementation");
  }
  const implementation = implementationValue;
  const source: MemoryQueryEvaluationGraphSource = Object.freeze({
    [PORT]: true as const,
    async load(contextValue, requestValue): Promise<unknown> {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      if (context.capability !== CAPABILITY) fail("capability_denied");
      return Reflect.apply(implementation, undefined, [context, exactRequest(requestValue)]);
    },
  });
  sources.add(source);
  return source;
};

export const inspectMemoryQueryEvaluationGraphSource = (
  value: unknown,
): MemoryQueryEvaluationGraphSource => {
  if (value === null || typeof value !== "object" || isProxy(value) || !sources.has(value)) {
    fail("unverified_source");
  }
  return value as MemoryQueryEvaluationGraphSource;
};
