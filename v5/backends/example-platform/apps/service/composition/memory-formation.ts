// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMCORE-013)
import type { Database } from "bun:sqlite";

import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../../core/consolidate/execution-policy";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import {
  GROUNDED_EXTRACTION_PROMPT_VERSION,
  GROUNDED_MENTION_STRATEGY_VERSION,
} from "../../../core/extract/grounded";
import type { UserAssertedStmNote } from "../../../core/stm/note";
import { SqliteLedger } from "../../../drivers/sqlite";
import type { AccountControlProjectionStore } from "../control/projection-store";
import {
  createLocalApplicationAuthorizer,
  type LocalApplicationAuthorizer,
} from "../auth/local-application-authorization";
import { composeIntegratorStmWrite, materializeIntegratorStmWrite } from "./integrator-stm-write";
import { defineListenFormationIngestion } from "../listen/formation-ingestion";
import {
  defineListenFormationOutboxConsumer,
} from "../listen/formation-outbox-consumer";
import {
  createInMemoryListenFormationOutbox,
} from "../listen/in-memory-formation-outbox";
import { createScriptedFormationModel } from "../model/scripted-formation-model";
import { createInMemoryDurableMemoryWorkStores } from "../stores/in-memory-durable-memory-work";
import type { ListenSessionRecord, ListenStore } from "../stores/listen-store";
import {
  CONSOLIDATION_WORK_KINDS,
  defineConsolidationWorkAdapter,
  defineConsolidationWorkService,
  type ConsolidationWorkKind,
} from "../workers/consolidation-work-service";
import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from "../workers/durable-memory-graph-plan";
import { defineFormationWorkDispatch } from "../workers/formation-work-dispatch";
import { defineFormationWorkService } from "../workers/formation-work-service";
import { promoteLocalVisibleClaims } from "./local-visible-promotion";
import { sealListenFormationFinalization } from "../listen/formation-ingestion";

export type LocalMemoryFormationMode = "wired" | "accept-only" | "formation-without-promotion";

export interface LocalMemoryFormationDrainReport {
  readonly outbox: { readonly kind: string };
  readonly formation: { readonly kind: string };
  readonly consolidation: { readonly kind: string };
  readonly promotion: { readonly promoted: number; readonly predicates: readonly string[] };
}

export interface LocalMemoryFormation {
  readonly wired: boolean;
  readonly mode: LocalMemoryFormationMode;
  lastDrain: LocalMemoryFormationDrainReport | null;
  ingestUserNote(input: {
    readonly note: UserAssertedStmNote;
    readonly account_epoch: number;
    readonly now_epoch_seconds: number;
  }): Promise<void>;
  enqueueListenFinalization(input: {
    readonly accountId: string;
    readonly session: ListenSessionRecord;
  }): void;
  drain(input: {
    readonly accountId: string;
    readonly accountEpoch: number;
    readonly nowEpochSeconds: number;
  }): Promise<LocalMemoryFormationDrainReport>;
}

export interface LocalMemoryFormationOptions {
  readonly db: Database;
  readonly ownerAccountId: string;
  readonly accountTimezone: string;
  readonly control: AccountControlProjectionStore;
  readonly listen: ListenStore;
  readonly mode?: LocalMemoryFormationMode;
}

const FORMATION_LEASE_SECONDS = 20;
const LOCAL_GENERATION = "local-scripted-v1";

export const composeLocalMemoryFormation = (
  options: LocalMemoryFormationOptions,
): LocalMemoryFormation => {
  const mode = options.mode ?? "wired";
  const ledger = new SqliteLedger(options.db);
  const authorizer: LocalApplicationAuthorizer = createLocalApplicationAuthorizer();
  const model = createScriptedFormationModel();
  const work = createInMemoryDurableMemoryWorkStores(ledger, FORMATION_LEASE_SECONDS);
  const outbox = createInMemoryListenFormationOutbox();

  const formationStrategy = registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: "strategy:formation:local-scripted",
    work_kind: "formation",
    coordinates: {
      strategy_version: "formation:local-v1",
      model_version: "scripted:v1",
      prompt_version: GROUNDED_EXTRACTION_PROMPT_VERSION,
      policy_version: "policy:v1",
      code_version: "code:v1",
      schema_version: "schema:v1",
      tokenizer_version: "none",
      tool_version: "none",
      result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
      speaker_strategy_version: GROUNDED_MENTION_STRATEGY_VERSION,
      boundary_strategy_version: "v4",
    },
  });
  const formationPolicy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:formation:local-v1",
    work_kind: "formation",
    unit_kind: "work",
    key_version: "assignment-key:local-v1",
    authority_strategy_id: formationStrategy.strategy_id,
    shadow_candidates: [],
  }, [formationStrategy]);
  const assigner = createMemoryStrategyAssigner(new Uint8Array(32).fill(11));
  const executionPolicy = registerDurableMemoryWorkExecutionPolicy({
    version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
    policy_id: "execution-policy:formation:local-v1",
    work_kind: "formation",
    execution_contract_digest: formationStrategy.execution_contract_digest,
    max_attempts: 3,
    lease_duration_seconds: FORMATION_LEASE_SECONDS,
    retry_delays_seconds: [10, 30],
  });

  const formation = defineFormationWorkService({
    acceptance_repository: work.acceptance,
    execution_repository: work.execution,
    result_repository: work.results,
    success_repository: work.success,
    input_repository: work.formationInput,
    resolve_strategy: async (job) => job.work_kind === "formation" ? formationStrategy : null,
    formation: {
      resolve_model: async () => model,
      load_current_parent: async (_context, job) => {
        const head = ledger.graphHead(job.owner_account_id);
        return { kind: "found" as const, parent_commit: head?.commit_id ?? null };
      },
      classify_model_error: () => "model_response_invalid",
    },
    max_parent_rematerializations: 2,
  });
  const formationDispatch = defineFormationWorkDispatch({
    execution_repository: work.execution,
    formation,
  });
  const noteIngestion = composeIntegratorStmWrite(formation);
  const listenIngestion = defineListenFormationIngestion(formation);
  const listenConsumer = defineListenFormationOutboxConsumer({
    repository: outbox.repository,
    load_ingestion_request: async (_context, payload) => {
      const graph = ledger.snapshot(payload.owner_account_id);
      return {
        finalization: payload.finalization,
        graph_snapshot: graph,
        source_language: "en",
        account_timezone: options.accountTimezone,
        reference_clock_query_at: payload.finalization.ended_at,
        policy_version: LOCAL_GENERATION,
        predicate_alias_generation: LOCAL_GENERATION,
        authorization_generation: LOCAL_GENERATION,
        stm_generation: String(graph.graph_generation ?? 0),
        strategy_assignment: assigner.assign({
          owner_account_id: payload.owner_account_id,
          unit_ref: payload.formation_work_id,
          policy: formationPolicy,
          strategies: [formationStrategy],
        }),
        execution_policy: executionPolicy,
        accepted_at_event_time: Math.floor(Date.parse(payload.finalization.ended_at) / 1_000),
      };
    },
    formation: listenIngestion,
  });

  const consolidationAdapters = Object.fromEntries(CONSOLIDATION_WORK_KINDS.map((kind) => [
    kind,
    defineConsolidationWorkAdapter(kind, {
      produce: async () => ({ kind: "failed" as const, error_code: "dependency_unavailable" }),
      materialize: async () => ({ kind: "failed" as const, error_code: "dependency_unavailable" }),
    }),
  ])) as Record<ConsolidationWorkKind, ReturnType<typeof defineConsolidationWorkAdapter>>;
  const consolidation = defineConsolidationWorkService({
    execution_repository: work.execution,
    result_repository: work.results,
    success_repository: work.success,
    resolve_strategy: async () => null,
    adapters: consolidationAdapters,
    max_parent_rematerializations: 2,
  });

  const graphCoordinates = (ownerAccountId: string, nowIso: string) => {
    const graph = ledger.snapshot(ownerAccountId);
    return {
      graph_snapshot: graph,
      source_language: "en" as const,
      account_timezone: options.accountTimezone,
      reference_clock_query_at: nowIso,
      policy_version: LOCAL_GENERATION,
      predicate_alias_generation: LOCAL_GENERATION,
      authorization_generation: LOCAL_GENERATION,
      stm_generation: String(graph.graph_generation ?? 0),
    };
  };

  const drain = async (input: {
    readonly accountId: string;
    readonly accountEpoch: number;
    readonly nowEpochSeconds: number;
  }): Promise<LocalMemoryFormationDrainReport> => {
    const acceptContext = authorizer.issue({
      account_id: input.accountId,
      account_epoch: input.accountEpoch,
      capability: "memories.work.accept",
      now_epoch_seconds: input.nowEpochSeconds,
    });
    const executeContext = authorizer.issue({
      account_id: input.accountId,
      account_epoch: input.accountEpoch,
      capability: "memories.work.execute",
      now_epoch_seconds: input.nowEpochSeconds,
    });
    let outboxKind = "skipped";
    let formationKind = "skipped";
    let consolidationKind = "skipped";
    let promotion = { promoted: 0, predicates: [] as readonly string[] };
    if (mode !== "accept-only") {
      for (let step = 0; step < 8; step += 1) {
        const outboxOutcome = await listenConsumer.runNext(acceptContext);
        outboxKind = outboxOutcome.kind;
        if (outboxOutcome.kind !== "accepted") break;
      }
      for (let step = 0; step < 8; step += 1) {
        const formationOutcome = await formationDispatch.runNext(executeContext);
        if (formationOutcome.kind === "idle") break;
        formationKind = formationOutcome.kind;
      }
      const consolidationOutcome = await consolidation.runNext(executeContext);
      consolidationKind = consolidationOutcome.kind;
      if (mode === "wired") {
        promotion = promoteLocalVisibleClaims(
          ledger,
          input.accountId,
          options.accountTimezone,
        );
      }
    }
    return Object.freeze({
      outbox: { kind: outboxKind },
      formation: { kind: formationKind },
      consolidation: { kind: consolidationKind },
      promotion: Object.freeze({
        promoted: promotion.promoted,
        predicates: promotion.predicates,
      }),
    });
  };

  let drainChain = Promise.resolve();
  const serializedDrain = (
    input: {
      readonly accountId: string;
      readonly accountEpoch: number;
      readonly nowEpochSeconds: number;
    },
  ): Promise<LocalMemoryFormationDrainReport> => {
    const run = drainChain.then(() => drain(input));
    drainChain = run.then(() => undefined, () => undefined);
    return run;
  };

  const pipeline: LocalMemoryFormation = {
    wired: mode === "wired",
    mode,
    lastDrain: null,
    async ingestUserNote(input) {
      const write = materializeIntegratorStmWrite({
        operation: "create",
        owner_account_id: input.note.owner_account_id,
        write_id: input.note.write_id,
        content: input.note.content,
        write_door: input.note.metadata.write_door,
        client_write_ref: input.note.metadata.client_write_ref,
        submitted_at: input.note.metadata.submitted_at,
      });
      const context = authorizer.issue({
        account_id: input.note.owner_account_id,
        account_epoch: input.account_epoch,
        capability: "memories.work.accept",
        now_epoch_seconds: input.now_epoch_seconds,
      });
      const coords = graphCoordinates(input.note.owner_account_id, input.note.metadata.submitted_at);
      const outcome = await noteIngestion.ingest(context, write, {
        ...coords,
        strategy_assignment: assigner.assign({
          owner_account_id: input.note.owner_account_id,
          unit_ref: write.note.formation_work_id,
          policy: formationPolicy,
          strategies: [formationStrategy],
        }),
        execution_policy: executionPolicy,
        accepted_at_event_time: input.now_epoch_seconds,
      });
      if (outcome.kind !== "accepted" && outcome.kind !== "replayed") {
        throw new TypeError(`stm note formation ingest ${outcome.kind}`);
      }
      if (mode !== "accept-only") {
        pipeline.lastDrain = await serializedDrain({
          accountId: input.note.owner_account_id,
          accountEpoch: input.account_epoch,
          nowEpochSeconds: input.now_epoch_seconds,
        });
      }
    },
    enqueueListenFinalization(input) {
      const segments = options.listen.listSegments(input.accountId, input.session.id);
      const finalization = sealListenFormationFinalization({
        owner_account_id: input.accountId,
        session: input.session,
        segments,
      });
      outbox.enqueue(finalization);
      if (mode !== "accept-only") {
        const projection = options.control.read(input.accountId);
        const endedAt = input.session.endedAt ?? input.session.updatedAt;
        void serializedDrain({
          accountId: input.accountId,
          accountEpoch: projection?.account_epoch ?? 0,
          nowEpochSeconds: Math.floor(Date.parse(endedAt) / 1_000),
        }).then((report) => {
          pipeline.lastDrain = report;
        }).catch(() => {});
      }
    },
    async drain(input) {
      const report = await serializedDrain(input);
      pipeline.lastDrain = report;
      return report;
    },
  };
  return pipeline;
};
