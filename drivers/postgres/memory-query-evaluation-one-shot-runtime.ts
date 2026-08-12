import { isProxy } from "node:util/types";

import type { AuthorizedLedgerWriteContext } from
  "../../apps/service/auth/authorized-context";
import {
  composeMemoryQueryEvaluation,
  type MemoryQueryEvaluationCompositionConfig,
} from
  "../../apps/service/composition/memory-query-evaluation";
import {
  materializeMemoryQueryEvaluationInput,
  type MemoryQueryEvaluationInput,
  type MemoryQueryEvaluationInputStageOutcome,
} from "../../apps/service/stores/memory-query-evaluation-input-repository";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresAuthoritativeGraphSnapshotRepository } from
  "./authoritative-graph-snapshot";
import {
  createPostgresMemoryReadGroundingRepository,
  createPostgresMemoryShadowResultRepository,
} from "./memory-experiment-repository";
import {
  createPostgresMemoryQueryEvaluationGraphSource,
  createPostgresMemoryQueryEvaluationInputRepository,
} from "./memory-query-evaluation-source";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
} from "./transaction";

const RUNTIME_PORT: unique symbol = Symbol("postgres-memory-query-evaluation-one-shot-runtime");
const INPUT_REF = /^mqir1_[a-f0-9]{64}$/;
const TIMEZONE = /^[\x21-\x7e]{1,128}$/;
const MAX_QUERY_CODE_POINTS = 4_096;
type QueryCoordinator = ReturnType<typeof composeMemoryQueryEvaluation>;
type PairedQueryGroundingRequest = Parameters<QueryCoordinator["run"]>[1];
type PairedQueryGroundingOutcome = Awaited<ReturnType<QueryCoordinator["run"]>>;

export interface PostgresMemoryQueryEvaluationInputBody {
  readonly input_ref: string;
  readonly query_text: string;
  readonly account_timezone: string;
}

export type PostgresMemoryQueryEvaluationInputOutcome =
  | MemoryQueryEvaluationInputStageOutcome
  | Readonly<{ kind: "source_unavailable" }>;

export interface PostgresMemoryQueryEvaluationOneShotRuntimeOptions {
  readonly pool: PostgresTransactionPool;
  readonly codec_root_secret: Uint8Array;
  readonly produce: MemoryQueryEvaluationCompositionConfig["produce"];
  readonly observability?: PostgresTransactionObservability;
}

export interface PostgresMemoryQueryEvaluationOneShotRuntime {
  readonly [RUNTIME_PORT]: true;
  stageInput(
    context: AuthorizedLedgerWriteContext,
    body: PostgresMemoryQueryEvaluationInputBody,
  ): Promise<PostgresMemoryQueryEvaluationInputOutcome>;
  run(
    context: AuthorizedLedgerWriteContext,
    request: PairedQueryGroundingRequest,
  ): Promise<PairedQueryGroundingOutcome>;
}

const inputBody = (value: PostgresMemoryQueryEvaluationInputBody): PostgresMemoryQueryEvaluationInputBody => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("postgres query evaluation runtime invalid_input");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const expected = ["account_timezone", "input_ref", "query_text"];
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== expected.length
    || (keys as string[]).sort().some((key, index) => key !== expected[index])) {
    throw new TypeError("postgres query evaluation runtime invalid_input");
  }
  for (const key of expected) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      throw new TypeError("postgres query evaluation runtime invalid_input");
    }
  }
  const inputRef = descriptors.input_ref!.value;
  const queryText = descriptors.query_text!.value;
  const timezone = descriptors.account_timezone!.value;
  if (typeof inputRef !== "string" || !INPUT_REF.test(inputRef)
    || typeof queryText !== "string" || queryText.length === 0 || queryText !== queryText.trim()
    || [...queryText].length > MAX_QUERY_CODE_POINTS || /[\p{Cs}\u0000]/u.test(queryText)
    || typeof timezone !== "string" || !TIMEZONE.test(timezone)) {
    throw new TypeError("postgres query evaluation runtime invalid_input");
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: timezone }).format(0);
  } catch {
    throw new TypeError("postgres query evaluation runtime invalid_input");
  }
  return Object.freeze({
    input_ref: inputRef,
    query_text: queryText,
    account_timezone: timezone,
  });
};

const sourceFailure = (error: unknown): PostgresMemoryQueryEvaluationInputOutcome => {
  if (!(error instanceof PostgresRepositoryError)) {
    return Object.freeze({ kind: "source_unavailable" as const });
  }
  switch (error.code) {
    case "expired_context":
    case "stale_epoch":
    case "destination_inactive":
    case "lifecycle_inactive":
      return Object.freeze({ kind: "stale_context" as const, reason: error.code });
    case "credential_inactive":
    case "grant_inactive":
    case "capability_denied":
      return Object.freeze({ kind: "authorization_denied" as const, reason: error.code });
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    default:
      return Object.freeze({ kind: "source_unavailable" as const });
  }
};

/**
 * Route-free, explicitly invoked PostgreSQL read-experiment assembly.
 *
 * Construction adds no route, timer, polling loop, credential source, model
 * default, secret lookup, cache, promotion path, or product/graph mutation.
 */
export const createPostgresMemoryQueryEvaluationOneShotRuntime = (
  options: PostgresMemoryQueryEvaluationOneShotRuntimeOptions,
): PostgresMemoryQueryEvaluationOneShotRuntime => {
  const repositoryOptions = {
    pool: options.pool,
    ...(options.observability ? { observability: options.observability } : {}),
  };
  const inputs = createPostgresMemoryQueryEvaluationInputRepository(repositoryOptions);
  const graphs = createPostgresAuthoritativeGraphSnapshotRepository(repositoryOptions);
  const coordinator = composeMemoryQueryEvaluation({
    graph_source: createPostgresMemoryQueryEvaluationGraphSource(repositoryOptions),
    codec_root_secret: options.codec_root_secret,
    result_repository: createPostgresMemoryShadowResultRepository(repositoryOptions),
    grounding_repository: createPostgresMemoryReadGroundingRepository(repositoryOptions),
    produce: options.produce,
  });

  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    async stageInput(context, bodyValue) {
      const body = inputBody(bodyValue);
      let graph;
      try {
        graph = await graphs.load(context);
      } catch (error) {
        return sourceFailure(error);
      }
      const input: Readonly<MemoryQueryEvaluationInput> = materializeMemoryQueryEvaluationInput(context, {
        input_ref: body.input_ref,
        query_text: body.query_text,
        account_timezone: body.account_timezone,
        graph_snapshot: graph,
      });
      return inputs.stage(context, input);
    },
    run: (context, request) => coordinator.run(context, request),
  });
};
