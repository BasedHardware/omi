import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";

export const MODEL_PIPELINE_RESOURCE_VERSION = "model-pipeline-resource-v1" as const;
const RESOURCE_PORT: unique symbol = Symbol("model-pipeline-exclusivity");
const DIGEST = /^[a-f0-9]{64}$/;

export interface ModelPipelineResource {
  readonly version: typeof MODEL_PIPELINE_RESOURCE_VERSION;
  readonly resource_digest: string;
}

export type ModelPipelineExclusiveOutcome<Result> =
  | Readonly<{ kind: "completed"; value: Result }>
  | Readonly<{ kind: "busy" }>
  | Readonly<{ kind: "unavailable" }>;

export interface ModelPipelineExclusivity {
  readonly [RESOURCE_PORT]: true;
  runExclusive<Result>(
    resource: Readonly<ModelPipelineResource>,
    callback: (lossSignal: AbortSignal) => Promise<Result>,
  ): Promise<ModelPipelineExclusiveOutcome<Result>>;
}

export const assertModelPipelineExclusivity = (value: unknown): ModelPipelineExclusivity => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype
    || Object.getOwnPropertyDescriptor(value, RESOURCE_PORT)?.value !== true) {
    fail("invalid_port");
  }
  const method = Object.getOwnPropertyDescriptor(value, "runExclusive");
  if (!method || !("value" in method) || typeof method.value !== "function"
    || isProxy(method.value)) fail("invalid_port");
  return value as ModelPipelineExclusivity;
};

const fail = (code: string): never => { throw new TypeError(`model pipeline exclusivity ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_resource");
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) fail("invalid_resource");
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail("invalid_resource");
  }
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_resource");
  }
  return value as Record<string, unknown>;
};

export const parseModelPipelineResource = (value: unknown): Readonly<ModelPipelineResource> => {
  const input = exactRecord(value, ["version", "resource_digest"]);
  if (input["version"] !== MODEL_PIPELINE_RESOURCE_VERSION
    || typeof input["resource_digest"] !== "string"
    || !DIGEST.test(input["resource_digest"])) fail("invalid_resource");
  return Object.freeze({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: input["resource_digest"],
  });
};

/**
 * The provider credential owner supplies only a digest identifying its resource;
 * raw API keys and provider labels never cross this boundary.
 */
export const modelPipelineResourceFor = (
  providerResourceDigest: string,
): Readonly<ModelPipelineResource> => {
  if (!DIGEST.test(providerResourceDigest)) fail("invalid_provider_resource_digest");
  return Object.freeze({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: sha256CanonicalContent({
      contract_version: MODEL_PIPELINE_RESOURCE_VERSION,
      provider_resource_digest: providerResourceDigest,
    }),
  });
};

export const defineModelPipelineExclusivity = (
  implementation: <Result>(
    resource: Readonly<ModelPipelineResource>,
    callback: (lossSignal: AbortSignal) => Promise<Result>,
  ) => Promise<ModelPipelineExclusiveOutcome<Result>>,
): ModelPipelineExclusivity => {
  if (typeof implementation !== "function" || isProxy(implementation)) fail("invalid_implementation");
  return Object.freeze({
    [RESOURCE_PORT]: true as const,
    async runExclusive<Result>(resourceValue: Readonly<ModelPipelineResource>, callback: (lossSignal: AbortSignal) => Promise<Result>) {
      const resource = parseModelPipelineResource(resourceValue);
      if (typeof callback !== "function" || isProxy(callback)) fail("invalid_callback");
      let open = true;
      let callbackCalls = 0;
      const pending = new Set<Promise<Result>>();
      const guardedCallback = (lossSignal: AbortSignal): Promise<Result> => {
        if (!open || callbackCalls !== 0) return Promise.reject(new TypeError("model pipeline exclusivity callback_closed"));
        if (!(lossSignal instanceof AbortSignal)) {
          return Promise.reject(new TypeError("model pipeline exclusivity invalid_loss_signal"));
        }
        callbackCalls += 1;
        const invocation = Promise.resolve().then(() => callback(lossSignal));
        pending.add(invocation);
        void invocation.finally(() => pending.delete(invocation)).catch(() => undefined);
        return invocation;
      };
      let outcome: ModelPipelineExclusiveOutcome<Result>;
      try {
        outcome = await implementation(resource, guardedCallback);
      } finally {
        open = false;
        await Promise.allSettled([...pending]);
      }
      if (outcome === null || typeof outcome !== "object" || Array.isArray(outcome) || isProxy(outcome)
        || Object.getPrototypeOf(outcome) !== Object.prototype) fail("invalid_outcome");
      const kind = Object.getOwnPropertyDescriptor(outcome, "kind")?.value;
      if (kind === "busy" || kind === "unavailable") {
        if (kind === "busy" ? callbackCalls !== 0 : callbackCalls > 1) fail("invalid_outcome");
        exactRecord(outcome, ["kind"]);
        return Object.freeze({ kind }) as ModelPipelineExclusiveOutcome<Result>;
      }
      if (kind !== "completed") fail("invalid_outcome");
      if (callbackCalls !== 1) fail("invalid_outcome");
      const input = exactRecord(outcome, ["kind", "value"]);
      return Object.freeze({ kind, value: input["value"] as Result });
    },
  });
};
