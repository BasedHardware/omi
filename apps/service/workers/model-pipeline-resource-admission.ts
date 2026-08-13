import { isProxy } from "node:util/types";

import {
  assertModelPipelineExclusivity,
  defineModelPipelineExclusivity,
  parseModelPipelineResource,
  type ModelPipelineExclusiveOutcome,
  type ModelPipelineExclusivity,
  type ModelPipelineResource,
} from "./model-pipeline-exclusivity";

export const MODEL_PIPELINE_RESOURCE_ADMISSION_VERSION =
  "model-pipeline-resource-admission-v1" as const;

const ADMISSION_PORT: unique symbol = Symbol("model-pipeline-resource-admission");
const ADMITTED_EXCLUSIVITY_PORT: unique symbol = Symbol("admitted-model-pipeline-exclusivity");
const MINTED_ADMITTED_EXCLUSIVITY = new WeakSet<object>();
const DIGEST = /^[a-f0-9]{64}$/;
const MAX_RESOURCES = 1_024;

export interface ModelPipelineResourceManifestEntry {
  readonly resource_digest: string;
  readonly max_concurrency: 1;
}

export interface ModelPipelineResourceAdmission {
  readonly [ADMISSION_PORT]: true;
  admit(resource: Readonly<ModelPipelineResource>): Readonly<ModelPipelineResource> | null;
}

export interface AdmittedModelPipelineExclusivity extends ModelPipelineExclusivity {
  readonly [ADMITTED_EXCLUSIVITY_PORT]: true;
}

const fail = (code: string): never => {
  throw new TypeError(`model pipeline resource admission ${code}`);
};

const exactEntry = (value: unknown): Readonly<ModelPipelineResourceManifestEntry> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_manifest");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.length !== 2 || keys.some((key) => typeof key !== "string")
    || !("max_concurrency" in descriptors) || !("resource_digest" in descriptors)) {
    fail("invalid_manifest");
  }
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_manifest");
  }
  const resourceDigest = descriptors["resource_digest"]!.value;
  if (typeof resourceDigest !== "string" || !DIGEST.test(resourceDigest)
    || descriptors["max_concurrency"]!.value !== 1) fail("invalid_manifest");
  return Object.freeze({ resource_digest: resourceDigest, max_concurrency: 1 as const });
};

export const defineModelPipelineResourceAdmission = (
  entriesValue: readonly Readonly<ModelPipelineResourceManifestEntry>[],
): ModelPipelineResourceAdmission => {
  if (!Array.isArray(entriesValue) || isProxy(entriesValue)
    || Object.getPrototypeOf(entriesValue) !== Array.prototype
    || entriesValue.length === 0 || entriesValue.length > MAX_RESOURCES) fail("invalid_manifest");
  const descriptors = Object.getOwnPropertyDescriptors(entriesValue);
  if (Reflect.ownKeys(descriptors).length !== entriesValue.length + 1) fail("invalid_manifest");
  const entries = entriesValue.map((_entry, index) => {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_manifest");
    return exactEntry(descriptor.value);
  });
  for (let index = 0; index < entries.length; index += 1) {
    if (index > 0 && entries[index - 1]!.resource_digest >= entries[index]!.resource_digest) {
      fail("invalid_manifest");
    }
  }
  const allowed = new Set(entries.map((entry) => entry.resource_digest));
  return Object.freeze({
    [ADMISSION_PORT]: true as const,
    admit(resourceValue: Readonly<ModelPipelineResource>) {
      const resource = parseModelPipelineResource(resourceValue);
      return allowed.has(resource.resource_digest) ? resource : null;
    },
  });
};

export const assertModelPipelineResourceAdmission = (
  value: unknown,
): ModelPipelineResourceAdmission => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype
    || Object.getOwnPropertyDescriptor(value, ADMISSION_PORT)?.value !== true) fail("invalid_port");
  const method = Object.getOwnPropertyDescriptor(value, "admit");
  if (!method || !("value" in method) || typeof method.value !== "function" || isProxy(method.value)) {
    fail("invalid_port");
  }
  return value as ModelPipelineResourceAdmission;
};

/**
 * Binds a generic exclusivity implementation to one validated resource set.
 * Production code may obtain this brand only through the PostgreSQL manifest
 * composition; direct use is fenced to this module and tests.
 */
export const bindModelPipelineResourceAdmission = (
  exclusivityValue: ModelPipelineExclusivity,
  admissionValue: ModelPipelineResourceAdmission,
): AdmittedModelPipelineExclusivity => {
  const exclusivity = assertModelPipelineExclusivity(exclusivityValue);
  const admission = assertModelPipelineResourceAdmission(admissionValue);
  const admitted = defineModelPipelineExclusivity(async <Result>(
    resourceValue: Readonly<ModelPipelineResource>,
    callback: (lossSignal: AbortSignal) => Promise<Result>,
  ): Promise<ModelPipelineExclusiveOutcome<Result>> => {
    const resource = admission.admit(resourceValue);
    if (resource === null) return Object.freeze({ kind: "unavailable" as const });
    return exclusivity.runExclusive(resource, callback);
  });
  MINTED_ADMITTED_EXCLUSIVITY.add(admitted);
  return admitted as AdmittedModelPipelineExclusivity;
};

export const assertAdmittedModelPipelineExclusivity = (
  value: unknown,
): AdmittedModelPipelineExclusivity => {
  assertModelPipelineExclusivity(value);
  if (value === null || typeof value !== "object" || !MINTED_ADMITTED_EXCLUSIVITY.has(value)) {
    fail("invalid_admitted_exclusivity");
  }
  return value as AdmittedModelPipelineExclusivity;
};
