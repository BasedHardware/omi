import { isProxy } from "node:util/types";

import {
  assertAdmittedModelPipelineExclusivity,
  type AdmittedModelPipelineExclusivity,
} from "../workers/model-pipeline-resource-admission";

export const PRODUCTION_PROCESS_LOCKS_VERSION = "production-process-locks-v1" as const;
const DIGEST = /^[a-f0-9]{64}$/;

const fail = (code: string): never => { throw new TypeError(`production process locks ${code}`); };

/**
 * Production process composition binds qualification-manifest resource locks.
 * Serving model ids stay outside this tree; callers inject opaque digests from
 * a parser-minted manifest. Probe model names are never serving defaults.
 */
export const composeProductionProcessModelLocks = (
  resourceDigestsValue: readonly string[],
  exclusivityValue: AdmittedModelPipelineExclusivity,
): AdmittedModelPipelineExclusivity => {
  if (!Array.isArray(resourceDigestsValue) || isProxy(resourceDigestsValue)
    || resourceDigestsValue.length === 0) fail("missing_resources");
  const digests = resourceDigestsValue.map((value) => {
    if (typeof value !== "string" || !DIGEST.test(value)) fail("invalid_digest");
    return value;
  });
  if (new Set(digests).size !== digests.length) fail("duplicate_digest");
  return assertAdmittedModelPipelineExclusivity(exclusivityValue);
};
