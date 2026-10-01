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
  inspectMemoryQueryEvaluationGraphSource,
  type MemoryQueryEvaluationGraphSource,
} from "../stores/memory-query-evaluation-graph-source";
import {
  defineMemoryAuthorizedQueryGroundingProducer,
  type AuthorizedQueryModelRequest,
  type AuthorizedQueryModelOutcome,
} from "../workers/memory-authorized-query-grounding-producer";
import {
  defineMemoryOwnerQueryEvidenceSource,
} from "../workers/memory-owner-query-evidence-source";
import {
  defineMemoryPairedQueryGroundingCoordinator,
  type MemoryPairedQueryGroundingCoordinator,
} from "../workers/memory-paired-query-grounding-coordinator";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";

export interface MemoryQueryEvaluationCompositionConfig {
  readonly graph_source: MemoryQueryEvaluationGraphSource;
  readonly codec_root_secret: Uint8Array;
  readonly result_repository: MemoryShadowResultRepository;
  readonly grounding_repository: MemoryReadGroundingRepository;
  readonly produce: (
    request: AuthorizedQueryModelRequest,
    lossSignal?: AbortSignal,
  ) => Promise<AuthorizedQueryModelOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`memory query evaluation composition ${code}`); };
const MIN_ROOT_SECRET_BYTES = 32;
const MAX_ROOT_SECRET_BYTES = 4_096;

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

const copyRootSecret = (value: unknown): Uint8Array => {
  if (!(value instanceof Uint8Array) || isProxy(value)
    || (Object.getPrototypeOf(value) !== Uint8Array.prototype && !Buffer.isBuffer(value))
    || value.buffer instanceof SharedArrayBuffer
    || value.byteLength < MIN_ROOT_SECRET_BYTES
    || value.byteLength > MAX_ROOT_SECRET_BYTES) fail("invalid_config");
  const copied = new Uint8Array(value.byteLength);
  copied.set(value);
  return copied;
};

export const composeMemoryQueryEvaluation = (
  configValue: MemoryQueryEvaluationCompositionConfig,
): MemoryPairedQueryGroundingCoordinator => {
  const config = exactRecord(configValue, [
    "graph_source", "codec_root_secret", "result_repository", "grounding_repository", "produce",
  ]);
  let graphSource: MemoryQueryEvaluationGraphSource;
  try {
    graphSource = inspectMemoryQueryEvaluationGraphSource(config["graph_source"]);
  } catch {
    return fail("invalid_config");
  }
  const codecRootSecret = copyRootSecret(config["codec_root_secret"]);
  const resultRepository = assertMemoryShadowResultRepository(config["result_repository"]);
  const groundingRepository = assertMemoryReadGroundingRepository(config["grounding_repository"]);
  const evidenceSource = defineMemoryOwnerQueryEvidenceSource({
    load_graph: (context, request) => graphSource.load(context, request),
    encode_trace_ref: ({ reader_projection_digest, evidence_closure_digest }) =>
      createReaderScopedOpaqueCodecs({
        root_secret: codecRootSecret,
        reader_projection_digest,
      }).encodeTraceRef(evidence_closure_digest),
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
