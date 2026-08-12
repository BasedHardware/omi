import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import {
  defineFormationWorkInputRepository,
  formationWorkInputStageRequestDigest,
  materializeStagedFormationWorkInput,
} from "./formation-work-input-repository";
import {
  FORMATION_INPUT_SNAPSHOT_VERSION,
  formationWorkInputManifest,
  parseFormationInputSnapshot,
} from "./formation-work-producer";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability: "memories.work.accept" | "memories.work.execute") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: capability === "memories.work.accept" ? "ingestion:one" : "worker:one",
  account_id: owner, application_id: "app:formation", credential_id: "credential:one",
  credential_generation: 1, capability, grant_id: "grant:one", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 90, expires_at_epoch_seconds: 900,
  authorization_state_digest: digest("a"),
}, 100);

const snapshot = (excerpt = "Alice uses Atlas") => parseFormationInputSnapshot({
  version: FORMATION_INPUT_SNAPSHOT_VERSION,
  owner_account_id: owner, work_id: "job:formation:one", session_id: "session:one",
  input_frontier: "0", graph_frontier: 0, observed_at: "2026-08-12T00:00:00Z",
  source_language: "en", account_timezone: "UTC",
  reference_clock: {
    query_at: "2026-08-12T00:00:00Z", capture_at: "2026-08-12T00:00:00Z",
  },
  context: {
    frontier: {
      graph_head: "0", policy_version: "policy:v1", predicate_alias_generation: "alias:0",
      authorization_generation: "authorization:0", stm_generation: "stm:0",
    },
    entity_candidates: [], predicate_signatures: [], open_propositions: [],
  },
  predicate_registry: [], entity_registry: [], target_evidence_ids: ["evidence:one"],
  evidence: [{
    evidence_id: "evidence:one", event_revision_id: "event:one:r1",
    source_unit_ref: "unit:one", range: { start: 0, end: excerpt.length }, excerpt,
    source_identity_ref: {
      namespace_instance_ref: "source:one", local_key: "speaker:unknown",
      producer: { producer_ref: null, contract_ref: null },
      asserted_identity: { domain: null, scope_ref: null },
    },
    speaker_rendering: null, source_local_mention_ref: null, state: "active",
    source_trust: "test", policy_labels: [], source_independence_key: "capture:one",
  }],
  events: [{
    event_id: "event:one", event_revision_id: "event:one:r1", owner_account_id: owner,
    capture_session_id: "session:one", stream_id: "stream:one", event_kind: "text",
    payload_schema_ref: "text:v1", schema_version: "schema:v1", payload: {},
    event_time: "2026-08-12T00:00:00Z", ingest_time: "2026-08-12T00:00:01Z",
    source_sequence: 0, evidence_addressable_refs: ["evidence:one"], source_trust: "test",
    policy_labels: [], canonical_redacted_hash: digest("e"),
  }],
  entities: [], identity_authorizations: [], identity_authority_context: null,
});

const pending = () => {
  const input = snapshot();
  return acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION, job_id: input.work_id, owner_account_id: owner,
    account_epoch: 7, lifecycle_state: "active", deletion_epoch: null,
    work_kind: "formation", input_frontier: input.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(formationWorkInputManifest(input)),
    execution_contract_digest: digest("c"), accepted_at_event_time: 100, max_attempts: 2,
  });
};

const request = () => {
  const body = { pending_job: pending(), snapshot: snapshot() };
  return { ...body, request_digest: formationWorkInputStageRequestDigest(body) };
};

describe("formation input repository contract", () => {
  test("stages exact input, replays it, and reloads it for a later worker process", async () => {
    let stored: ReturnType<typeof materializeStagedFormationWorkInput> | null = null;
    const repository = defineFormationWorkInputRepository({
      async stage(_authorized, value) {
        const expected = materializeStagedFormationWorkInput(value);
        if (stored) return { kind: "replayed", input: stored };
        stored = expected;
        return { kind: "staged", input: expected };
      },
      async load() { return stored ? { kind: "found", input: stored } : { kind: "not_found" }; },
    });
    await expect(repository.stage(context("memories.work.accept"), request()))
      .resolves.toMatchObject({ kind: "staged", input: { snapshot_digest: expect.any(String) } });
    await expect(repository.stage(context("memories.work.accept"), request()))
      .resolves.toMatchObject({ kind: "replayed" });
    const leased = leaseDurableMemoryWork(pending(), "worker:one", 101, 20);
    await expect(repository.load(context("memories.work.execute"), leased))
      .resolves.toMatchObject({ kind: "found", snapshot: { evidence: [{ excerpt: "Alice uses Atlas" }] } });
  });

  test("changed snapshot, hostile request, and wrong capability fail before implementation", async () => {
    let calls = 0;
    const repository = defineFormationWorkInputRepository({
      async stage(_authorized, value) {
        calls += 1;
        return { kind: "staged", input: materializeStagedFormationWorkInput(value) };
      },
      async load() { calls += 1; return { kind: "not_found" }; },
    });
    const changed = { ...request(), snapshot: snapshot("Mallory uses Atlas") };
    await expect(repository.stage(context("memories.work.accept"), changed))
      .rejects.toThrow("input_digest_mismatch");
    await expect(repository.stage(context("memories.work.execute"), request()))
      .rejects.toThrow("capability_denied");
    await expect(repository.stage(context("memories.work.accept"), {
      ...request(), request_digest: digest("f"),
    })).rejects.toThrow("request_digest_mismatch");
    let getterCalls = 0;
    const hostile = Object.defineProperty({
      snapshot: snapshot(), request_digest: request().request_digest,
    }, "pending_job", {
      enumerable: true,
      get() { getterCalls += 1; return pending(); },
    });
    await expect(repository.stage(context("memories.work.accept"), hostile as never))
      .rejects.toThrow("invalid_shape");
    expect(getterCalls).toBe(0);
    expect(calls).toBe(0);
  });
});
