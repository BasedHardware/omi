import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../../core/consolidate/execution-policy";
import {
  GROUNDED_EXTRACTION_PROMPT_VERSION,
  GROUNDED_MENTION_STRATEGY_VERSION,
} from "../../../core/extract/grounded";
import type { Evidence, L1Event } from "../../../core/schema";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkAcceptanceRepository,
  defineDurableMemoryWorkExecutionRepository,
  durableMemoryWorkInputManifestDigest,
} from "../stores/durable-memory-work-repository";
import { defineDurableMemoryWorkResultRepository } from "../stores/durable-memory-work-result-repository";
import { defineDurableMemoryWorkSuccessRepository } from "../stores/durable-memory-work-success-repository";
import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from "./durable-memory-graph-plan";
import {
  FORMATION_INPUT_SNAPSHOT_VERSION,
  formationWorkInputManifest,
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "./formation-work-producer";
import { defineFormationWorkService } from "./formation-work-service";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (
  capability: "memories.work.accept" | "memories.work.execute",
  principal = capability === "memories.work.execute" ? "worker:one" : "principal:ingestion",
) => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: principal,
  account_id: "account:alice",
  application_id: "app:formation",
  credential_id: "credential:one",
  credential_generation: 1,
  capability,
  grant_id: "grant:one",
  grant_version: 1,
  account_epoch: 7,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const strategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:formation:authority",
  work_kind: "formation",
  coordinates: {
    strategy_version: "formation:v1", model_version: "fake:v1",
    prompt_version: GROUNDED_EXTRACTION_PROMPT_VERSION, policy_version: "policy:v1",
    code_version: "code:v1", schema_version: "schema:v1",
    tokenizer_version: "none", tool_version: "none",
    result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
    speaker_strategy_version: GROUNDED_MENTION_STRATEGY_VERSION,
    boundary_strategy_version: "v4",
  },
});

const policy = defineMemoryStrategyAssignmentPolicy({
  policy_id: "policy:formation:v1", work_kind: "formation", unit_kind: "work",
  key_version: "assignment-key:v1", authority_strategy_id: strategy.strategy_id,
  shadow_candidates: [],
}, [strategy]);

const executionPolicy = registerDurableMemoryWorkExecutionPolicy({
  version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  policy_id: "execution-policy:formation:v1",
  work_kind: "formation",
  execution_contract_digest: strategy.execution_contract_digest,
  max_attempts: 3,
  lease_duration_seconds: 20,
  retry_delays_seconds: [10, 30],
});

const event: L1Event = {
  event_id: "event:one", event_revision_id: "event:one:r1",
  owner_account_id: "account:alice", capture_session_id: "session:one",
  stream_id: "stream:one", event_kind: "text", payload_schema_ref: "text:v1",
  schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:00Z",
  ingest_time: "2026-01-01T00:00:01Z", source_sequence: 0,
  evidence_addressable_refs: ["evidence:one"], source_trust: "test",
  policy_labels: [], canonical_redacted_hash: digest("e"),
};

const evidence: Evidence = {
  evidence_id: "evidence:one", event_revision_id: event.event_revision_id,
  source_unit_ref: "unit:one", range: { start: 0, end: 16 }, excerpt: "Alice uses Atlas",
  source_identity_ref: {
    namespace_instance_ref: "source:one", local_key: "speaker:unknown",
    producer: { producer_ref: null, contract_ref: null },
    asserted_identity: { domain: null, scope_ref: null },
  },
  speaker_rendering: null, source_local_mention_ref: null, state: "active",
  source_trust: "test", policy_labels: [], source_independence_key: "capture:one",
};

const snapshot = (): Readonly<FormationInputSnapshot> => parseFormationInputSnapshot({
  version: FORMATION_INPUT_SNAPSHOT_VERSION,
  owner_account_id: "account:alice", work_id: "job:formation:one",
  session_id: "session:one", input_frontier: "0", graph_frontier: 0,
  observed_at: "2026-01-01T00:00:00Z", source_language: "en", account_timezone: "UTC",
  reference_clock: { query_at: "2026-01-01T00:00:00Z", capture_at: "2026-01-01T00:00:00Z" },
  context: {
    frontier: {
      graph_head: "0", policy_version: "policy:v1", predicate_alias_generation: "alias:0",
      authorization_generation: "authorization:0", stm_generation: "stm:0",
    },
    entity_candidates: [], predicate_signatures: [], open_propositions: [],
  },
  predicate_registry: [], entity_registry: [], target_evidence_ids: [evidence.evidence_id],
  evidence: [evidence], events: [event], entities: [], identity_authorizations: [],
  identity_authority_context: null,
});

const leased = (workKind: "formation" | "promotion" = "formation") => {
  const input = snapshot();
  return leaseDurableMemoryWork(acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: workKind === "formation" ? input.work_id : "job:promotion:one",
    owner_account_id: input.owner_account_id,
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: workKind,
    input_frontier: input.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(formationWorkInputManifest(input)),
    execution_contract_digest: strategy.execution_contract_digest,
    accepted_at_event_time: 100,
    max_attempts: 3,
  }), "worker:one", 101, 20);
};

describe("formation work service composition", () => {
  test("joins exact acceptance to the formation executor without exposing components", async () => {
    const input = snapshot();
    const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(7)).assign({
      owner_account_id: input.owner_account_id, unit_ref: input.work_id,
      policy, strategies: [strategy],
    });
    let accepts = 0;
    const service = defineFormationWorkService({
      acceptance_repository: defineDurableMemoryWorkAcceptanceRepository(async (_authorized, request) => {
        accepts += 1;
        return { kind: "accepted", job: request.pending_job };
      }),
      execution_repository: defineDurableMemoryWorkExecutionRepository({
        leaseNext: async () => ({ kind: "none_available" }),
        load: async () => ({ kind: "not_found" }),
        recordFailure: async () => ({ kind: "ineligible_state" }),
        recoverExpired: async () => ({ kind: "not_expired" }),
      }),
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => ({ kind: "missing" }),
        stage: async () => ({ kind: "ineligible_state" }),
      }),
      success_repository: defineDurableMemoryWorkSuccessRepository(async () => ({ kind: "ineligible_state" })),
      resolve_strategy: async () => strategy,
      formation: {
        load_input: async () => ({ kind: "not_found" }),
        resolve_model: async () => null,
        load_current_parent: async () => ({ kind: "failed", error_code: "dependency_unavailable" }),
      },
      max_parent_rematerializations: 2,
    });
    await expect(service.accept(context("memories.work.accept"), {
      snapshot: input, strategy_assignment: assignment,
      execution_policy: executionPolicy, accepted_at_event_time: 100,
    })).resolves.toMatchObject({ kind: "accepted", job: { work_kind: "formation" } });
    expect(accepts).toBe(1);
    expect(Object.keys(service)).toEqual(["accept", "run"]);
  });

  test("runs only formation work and never records a failure against another work kind", async () => {
    const failures: string[] = [];
    let strategyResolutions = 0;
    let inputLoads = 0;
    const formationJob = leased();
    const service = defineFormationWorkService({
      acceptance_repository: defineDurableMemoryWorkAcceptanceRepository(async (_authorized, request) => ({
        kind: "accepted", job: request.pending_job,
      })),
      execution_repository: defineDurableMemoryWorkExecutionRepository({
        leaseNext: async () => ({ kind: "none_available" }),
        load: async () => ({ kind: "not_found" }),
        recordFailure: async (_authorized, request) => {
          failures.push(request.error_code);
          return {
            kind: "recorded",
            job: failDurableMemoryWork(
              formationJob,
              { worker_id: "worker:one", fence: formationJob.lease!.fence },
              102, request.error_code, 103,
            ),
          };
        },
        recoverExpired: async () => ({ kind: "not_expired" }),
      }),
      result_repository: defineDurableMemoryWorkResultRepository({
        load: async () => ({ kind: "missing" }),
        stage: async () => { throw new Error("must not stage missing input"); },
      }),
      success_repository: defineDurableMemoryWorkSuccessRepository(async () => {
        throw new Error("must not commit missing input");
      }),
      resolve_strategy: async () => { strategyResolutions += 1; return strategy; },
      formation: {
        load_input: async () => { inputLoads += 1; return { kind: "not_found" }; },
        resolve_model: async () => { throw new Error("must not resolve model without input"); },
        load_current_parent: async () => { throw new Error("must not load parent without input"); },
      },
      max_parent_rematerializations: 2,
    });

    await expect(service.run(context("memories.work.execute"), formationJob)).resolves.toMatchObject({
      kind: "failure_recorded", error_code: "dependency_unavailable",
      producer_calls: 1, materialization_attempts: 0,
    });
    expect({ strategyResolutions, inputLoads, failures }).toEqual({
      strategyResolutions: 1, inputLoads: 1, failures: ["dependency_unavailable"],
    });

    await expect(service.run(context("memories.work.execute"), leased("promotion"))).resolves.toEqual({
      kind: "stopped", stop_code: "ineligible_state",
      producer_calls: 0, materialization_attempts: 0,
    });
    expect({ strategyResolutions, inputLoads, failures }).toEqual({
      strategyResolutions: 1, inputLoads: 1, failures: ["dependency_unavailable"],
    });
  });
});
