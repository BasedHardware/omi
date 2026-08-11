import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import type { Evidence, L1Event } from "../../../core/schema";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { defineDurableMemoryWorkAcceptanceRepository } from "../stores/durable-memory-work-repository";
import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from "./durable-memory-graph-plan";
import {
  FORMATION_INPUT_SNAPSHOT_VERSION,
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "./formation-work-producer";
import { defineFormationWorkIngestion } from "./formation-work-ingestion";
import {
  GROUNDED_EXTRACTION_PROMPT_VERSION,
  GROUNDED_MENTION_STRATEGY_VERSION,
} from "../../../core/extract/grounded";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.work.accept", owner = "account:alice") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "principal:ingestion",
  account_id: owner,
  application_id: "app:ingestion",
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
    strategy_version: "formation:v1", model_version: "model:v1",
    prompt_version: GROUNDED_EXTRACTION_PROMPT_VERSION,
    policy_version: "policy:v1", code_version: "code:v1", schema_version: "schema:v1",
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

const assignment = (workId = "job:formation:one") =>
  createMemoryStrategyAssigner(new Uint8Array(32).fill(7)).assign({
    owner_account_id: "account:alice", unit_ref: workId, policy, strategies: [strategy],
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

const evidence = (excerpt: string): Evidence => ({
  evidence_id: "evidence:one", event_revision_id: event.event_revision_id,
  source_unit_ref: "unit:one", range: { start: 0, end: excerpt.length }, excerpt,
  source_identity_ref: {
    namespace_instance_ref: "source:one", local_key: "speaker:unknown",
    producer: { producer_ref: null, contract_ref: null },
    asserted_identity: { domain: null, scope_ref: null },
  },
  speaker_rendering: null, source_local_mention_ref: null, state: "active",
  source_trust: "test", policy_labels: [], source_independence_key: "capture:one",
});

const snapshot = (excerpt = "Alice uses Atlas"): Readonly<FormationInputSnapshot> => {
  const source = evidence(excerpt);
  return parseFormationInputSnapshot({
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
    predicate_registry: [], entity_registry: [], target_evidence_ids: [source.evidence_id],
    evidence: [source], events: [event], entities: [], identity_authorizations: [],
    identity_authority_context: null,
  });
};

describe("formation work ingestion", () => {
  test("accepts exact copied input before any producer and replays byte-identically", async () => {
    const stored = new Map<string, { digest: string; job: unknown }>();
    let calls = 0;
    const repository = defineDurableMemoryWorkAcceptanceRepository(async (_authorized, request) => {
      calls += 1;
      const prior = stored.get(request.pending_job.job_id);
      if (prior) return prior.digest === request.request_digest
        ? { kind: "replayed", job: prior.job }
        : { kind: "idempotency_conflict" };
      stored.set(request.pending_job.job_id, {
        digest: request.request_digest, job: request.pending_job,
      });
      return { kind: "accepted", job: request.pending_job };
    });
    const ingestion = defineFormationWorkIngestion(repository);
    const request = {
      snapshot: snapshot(), strategy_assignment: assignment(),
      accepted_at_event_time: 100, max_attempts: 3,
    };
    await expect(ingestion.accept(context(), request)).resolves.toMatchObject({
      kind: "accepted", job: { state: "pending", attempt: 0 },
    });
    await expect(ingestion.accept(context(), request)).resolves.toMatchObject({
      kind: "replayed", job: { state: "pending", attempt: 0 },
    });
    expect(calls).toBe(2);
    expect(Object.keys(ingestion)).toEqual(["accept"]);
  });

  test("same work id with changed evidence reaches storage as an idempotency conflict", async () => {
    let firstDigest: string | null = null;
    let calls = 0;
    const repository = defineDurableMemoryWorkAcceptanceRepository(async (_authorized, request) => {
      calls += 1;
      if (firstDigest === null) {
        firstDigest = request.request_digest;
        return { kind: "accepted", job: request.pending_job };
      }
      return request.request_digest === firstDigest
        ? { kind: "replayed", job: request.pending_job }
        : { kind: "idempotency_conflict" };
    });
    const ingestion = defineFormationWorkIngestion(repository);
    const base = { strategy_assignment: assignment(), accepted_at_event_time: 100, max_attempts: 3 };
    await ingestion.accept(context(), { ...base, snapshot: snapshot() });
    await expect(ingestion.accept(context(), {
      ...base, snapshot: snapshot("Mallory uses Atlas"),
    })).resolves.toEqual({ kind: "idempotency_conflict" });
    expect(calls).toBe(2);
  });

  test("capability, owner, schedule, and unminted assignment fail before repository access", async () => {
    let calls = 0;
    const ingestion = defineFormationWorkIngestion(
      defineDurableMemoryWorkAcceptanceRepository(async (_authorized, request) => {
        calls += 1;
        return { kind: "accepted", job: request.pending_job };
      }),
    );
    const base = {
      snapshot: snapshot(), strategy_assignment: assignment(),
      accepted_at_event_time: 100, max_attempts: 3,
    };
    await expect(ingestion.accept(context("memories.work.execute"), base)).rejects.toThrow("capability_denied");
    await expect(ingestion.accept(context("memories.work.accept", "account:bob"), base)).rejects.toThrow("coordinate_mismatch");
    await expect(ingestion.accept(context(), { ...base, max_attempts: 0 })).rejects.toThrow("invalid_schedule");
    await expect(ingestion.accept(context(), {
      ...base, strategy_assignment: structuredClone(base.strategy_assignment),
    })).rejects.toThrow("unminted_assignment");
    expect(calls).toBe(0);
  });
});
