import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { Evidence, L1Event } from "../../../core/schema";
import {
  GROUNDED_EXTRACTION_PROMPT_VERSION,
  GROUNDED_MENTION_STRATEGY_VERSION,
} from "../../../core/extract/grounded";
import type { WritingContext } from "../../../core/retrieve/writing-context";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  materializeStagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import { DeterministicFakeModel, type ModelInvokeRequest } from "../../../drivers/model/port";
import {
  DURABLE_MEMORY_GRAPH_PLAN_VERSION,
  normalizeDurableMemoryGraphPlan,
} from "./durable-memory-graph-plan";
import {
  FORMATION_INPUT_SNAPSHOT_VERSION,
  defineFormationWorkAdapter,
  formationWorkInputManifest,
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "./formation-work-producer";

const digest = (character: string): string => character.repeat(64);

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:one",
  account_id: "account:alice",
  application_id: "app:worker",
  credential_id: "credential:one",
  credential_generation: 1,
  capability: "memories.work.execute",
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
    speaker_strategy_version: GROUNDED_MENTION_STRATEGY_VERSION, boundary_strategy_version: "v4",
  },
});

const writingContext: WritingContext = {
  frontier: {
    graph_head: "0", policy_version: "policy:v1", predicate_alias_generation: "alias:0",
    authorization_generation: "authorization:0", stm_generation: "stm:0",
  },
  entity_candidates: [], predicate_signatures: [], open_propositions: [],
};

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
  source_unit_ref: "unit:one", range: { start: 0, end: 20 }, excerpt: "Alice uses Atlas now",
  source_identity_ref: {
    namespace_instance_ref: "source:one", local_key: "speaker:unknown",
    producer: { producer_ref: null, contract_ref: null },
    asserted_identity: { domain: null, scope_ref: null },
  },
  speaker_rendering: null, source_local_mention_ref: null, state: "active",
  source_trust: "test", policy_labels: [], source_independence_key: "capture:one",
};

const snapshot = (excerpt = evidence.excerpt!): Readonly<FormationInputSnapshot> =>
  parseFormationInputSnapshot({
    version: FORMATION_INPUT_SNAPSHOT_VERSION,
    owner_account_id: "account:alice", work_id: "job:formation:one",
    session_id: "session:one", input_frontier: "0", graph_frontier: 0,
    observed_at: "2026-01-01T00:00:00Z", source_language: "en", account_timezone: "UTC",
    reference_clock: { query_at: "2026-01-01T00:00:00Z", capture_at: "2026-01-01T00:00:00Z" },
    context: writingContext, predicate_registry: [], entity_registry: [],
    target_evidence_ids: [evidence.evidence_id],
    evidence: [{ ...evidence, excerpt, range: { start: 0, end: excerpt.length } }],
    events: [event], entities: [], identity_authorizations: [], identity_authority_context: null,
  });

const leased = (
  input: Readonly<FormationInputSnapshot>,
  registered = strategy,
) => leaseDurableMemoryWork(
  acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: input.work_id,
    owner_account_id: input.owner_account_id,
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: "formation",
    input_frontier: input.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(formationWorkInputManifest(input)),
    execution_contract_digest: registered.execution_contract_digest,
    accepted_at_event_time: 100,
    max_attempts: 3,
  }),
  "worker:one", 101, 20,
);

const model = (seen: string[]) => new DeterministicFakeModel((request: ModelInvokeRequest) => {
  seen.push(request.strategy);
  if (request.strategy === "grounded-extraction") return {
    claims: [{
      relation: "uses",
      arguments: [
        { slot_id: "person", role: "person", surface: "Alice" },
        { slot_id: "tool", role: "tool", surface: "Atlas" },
      ],
      polarity: "positive",
      temporal_expression: { kind: "absolute", granularity: "day", value: "2026-01-01" },
      evidence: "e1",
      observed_speaker_slot_id: null,
    }],
  };
  if (request.strategy === "local-handle-durable-entity") return { decision: "abstain" };
  if (request.strategy === "scope-role-binding") return {
    bindings: { person: null, tool: null }, scope: { locality: "durable", scope_ref: "global" },
  };
  if (request.strategy === "stm-ltm-unit-boundary") {
    expect(request.version).toBe("v4");
    return { decision: "accept_ltm" };
  }
  throw new Error(`unexpected strategy ${request.strategy}`);
});

describe("formation durable-work adapter", () => {
  test("one accepted snapshot produces total formation-v2 plus a staged parent-independent graph plan", async () => {
    const input = snapshot();
    const job = leased(input);
    const seen: string[] = [];
    const errors: string[] = [];
    const adapter = defineFormationWorkAdapter({
      load_input: async (authorized, loadedJob) => {
        expect(authorized.principal_id).toBe("worker:one");
        expect(loadedJob.job_id).toBe(job.job_id);
        return { kind: "found", snapshot: input };
      },
      resolve_model: async () => model(seen),
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
      classify_model_error: (error) => { errors.push(String(error)); return "model_response_invalid"; },
    });
    const produced = await adapter.produce(context(), job, strategy);
    expect(errors).toEqual([]);
    expect(produced.kind).toBe("produced");
    if (produced.kind !== "produced") throw new Error("expected produced result");
    const plan = normalizeDurableMemoryGraphPlan(produced.normalized_result) as unknown as {
      origin: unknown;
      revisions: readonly { kind: string; placement_status?: string }[];
    };
    expect(plan.origin).toMatchObject({
      kind: "formation",
      outcome: {
        work_id: job.job_id,
        candidate_count: 1,
        extraction_outcomes: [{ kind: "accepted", candidate_ref: "candidate:1" }],
        placement_outcomes: [{ kind: "abstained", reason_code: "placement_deferred" }],
      },
    });
    expect(plan.revisions.some((revision) => revision.kind === "mention")).toBe(true);
    expect(plan.revisions.some((revision) => revision.kind === "claim"
      && revision.placement_status === "provisional_abstained")).toBe(true);
    expect(seen.filter((edge) => edge === "grounded-extraction")).toHaveLength(1);
    expect(seen).not.toContain("mention-local-handle");

    const stageBody = {
      leased_job: job,
      result_contract_version: produced.result_contract_version,
      response_digest: produced.response_digest,
      normalized_result_digest: durableMemoryWorkNormalizedResultDigest(
        produced.result_contract_version, produced.normalized_result,
      ),
      normalized_result: produced.normalized_result,
    };
    const staged = materializeStagedDurableMemoryWorkResult({
      ...stageBody,
      request_digest: durableMemoryWorkResultStageRequestDigest(stageBody),
    });
    const materialized = await adapter.materialize(context(), job, staged, strategy);
    expect(materialized).toMatchObject({
      kind: "ready", result_kind: "successful",
      authoritative_append: { append_attempt: { expected_parent_commit: null } },
    });
  });

  test("changed copied evidence fails its accepted manifest before any model edge", async () => {
    const accepted = snapshot();
    const job = leased(accepted);
    const changed = snapshot("Mallory uses Atlas now");
    let resolvedModels = 0;
    const adapter = defineFormationWorkAdapter({
      load_input: async () => ({ kind: "found", snapshot: changed }),
      resolve_model: async () => { resolvedModels += 1; return model([]); },
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
    });
    await expect(adapter.produce(context(), job, strategy)).resolves.toEqual({
      kind: "failed", error_code: "dependency_unavailable",
    });
    expect(resolvedModels).toBe(0);
  });

  test("unregistered prompt, speaker, or boundary coordinates fail before input or model access", async () => {
    const input = snapshot();
    const job = leased(input);
    let dependencyCalls = 0;
    const adapter = defineFormationWorkAdapter({
      load_input: async () => { dependencyCalls += 1; return { kind: "found", snapshot: input }; },
      resolve_model: async () => { dependencyCalls += 1; return model([]); },
      load_current_parent: async () => ({ kind: "found", parent_commit: null }),
    });
    for (const coordinates of [
      { ...strategy.coordinates, prompt_version: "grounded-extraction-v5" },
      { ...strategy.coordinates, speaker_strategy_version: "surface-reinference-v0" },
      { ...strategy.coordinates, boundary_strategy_version: "v6" },
    ]) {
      const changed = registerMemoryStrategy({
        version: MEMORY_STRATEGY_VERSION,
        strategy_id: `strategy:changed:${coordinates.prompt_version}:${coordinates.speaker_strategy_version}:${coordinates.boundary_strategy_version}`,
        work_kind: "formation",
        coordinates,
      });
      const changedJob = leased(input, changed);
      await expect(adapter.produce(context(), changedJob, changed)).resolves.toEqual({
        kind: "failed", error_code: "dependency_unavailable",
      });
    }
    expect(dependencyCalls).toBe(0);
  });

  test("materialization reloads the current parent and never repeats production", async () => {
    const input = snapshot();
    const job = leased(input);
    const seen: string[] = [];
    let parent: string | null = null;
    const adapter = defineFormationWorkAdapter({
      load_input: async () => ({ kind: "found", snapshot: input }),
      resolve_model: async () => model(seen),
      load_current_parent: async () => ({ kind: "found", parent_commit: parent }),
    });
    const produced = await adapter.produce(context(), job, strategy);
    if (produced.kind !== "produced") throw new Error("expected produced result");
    const stageBody = {
      leased_job: job, result_contract_version: produced.result_contract_version,
      response_digest: produced.response_digest,
      normalized_result_digest: durableMemoryWorkNormalizedResultDigest(
        produced.result_contract_version, produced.normalized_result,
      ),
      normalized_result: produced.normalized_result,
    };
    const staged = materializeStagedDurableMemoryWorkResult({
      ...stageBody, request_digest: durableMemoryWorkResultStageRequestDigest(stageBody),
    });
    const initial = await adapter.materialize(context(), job, staged, strategy);
    parent = "commit:intervening";
    const advanced = await adapter.materialize(context(), job, staged, strategy);
    expect(initial.kind).toBe("ready");
    expect(advanced.kind).toBe("ready");
    if (initial.kind !== "ready" || advanced.kind !== "ready") throw new Error("expected ready");
    expect(initial.authoritative_append?.append_attempt.request_digest)
      .not.toBe(advanced.authoritative_append?.append_attempt.request_digest);
    expect(seen.filter((edge) => edge === "grounded-extraction")).toHaveLength(1);
  });
});
