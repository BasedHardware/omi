import { isProxy } from "node:util/types";

import {
  assertMemoryReadGroundingRepository,
  type MemoryReadGroundingRepository,
} from "../stores/memory-read-grounding-repository";
import {
  assertMemoryShadowResultRepository,
  type MemoryShadowResultRepository,
} from "../stores/memory-shadow-result-repository";
import {
  defineMemoryAuthorizedQueryGroundingProducer,
  type AuthorizedQueryModelRequest,
  type AuthorizedQueryModelOutcome,
} from "../workers/memory-authorized-query-grounding-producer";
import {
  defineMemoryOwnerQueryEvidenceSource,
  type MemoryOwnerQueryEvidenceSourceDependencies,
} from "../workers/memory-owner-query-evidence-source";
import {
  defineMemoryPairedQueryGroundingCoordinator,
  type MemoryPairedQueryGroundingCoordinator,
} from "../workers/memory-paired-query-grounding-coordinator";

export interface MemoryQueryEvaluationCompositionConfig {
  readonly load_graph: MemoryOwnerQueryEvidenceSourceDependencies["load_graph"];
  readonly encode_trace_ref: MemoryOwnerQueryEvidenceSourceDependencies["encode_trace_ref"];
  readonly result_repository: MemoryShadowResultRepository;
  readonly grounding_repository: MemoryReadGroundingRepository;
  readonly produce: (request: AuthorizedQueryModelRequest) => Promise<AuthorizedQueryModelOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`memory query evaluation composition ${code}`); };

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

export const composeMemoryQueryEvaluation = (
  configValue: MemoryQueryEvaluationCompositionConfig,
): MemoryPairedQueryGroundingCoordinator => {
  const config = exactRecord(configValue, [
    "load_graph", "encode_trace_ref", "result_repository", "grounding_repository", "produce",
  ]);
  const resultRepository = assertMemoryShadowResultRepository(config["result_repository"]);
  const groundingRepository = assertMemoryReadGroundingRepository(config["grounding_repository"]);
  const evidenceSource = defineMemoryOwnerQueryEvidenceSource({
    load_graph: config["load_graph"] as MemoryOwnerQueryEvidenceSourceDependencies["load_graph"],
    encode_trace_ref: config["encode_trace_ref"] as MemoryOwnerQueryEvidenceSourceDependencies["encode_trace_ref"],
  });
  const producer = defineMemoryAuthorizedQueryGroundingProducer({
    evidence_source: evidenceSource,
    result_repository: resultRepository,
    grounding_repository: groundingRepository,
    produce: config["produce"] as MemoryQueryEvaluationCompositionConfig["produce"],
  });
  return defineMemoryPairedQueryGroundingCoordinator({
    producer,
    pair_repository: resultRepository,
  });
};
