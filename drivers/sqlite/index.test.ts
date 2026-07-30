import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { prepareDerivation, type AtomicGraphTransition, type DerivationVersions } from "../../core/ledger";
import { projectTreeInputSnapshot } from "../../core/retrieve";
import { IdempotencyConflictError, SqliteLedger } from "./index";

const versions: DerivationVersions = { strategy_version: "placement-v1", model_version: "none", prompt_version: "none", policy_version: "p1", code_version: "c1", schema_version: "s1", tokenizer_version: "none", tool_version: "none" };
const entity = { entity_id: "entity:alice", owner_account_id: "owner-1", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] };
const identity = { constraint_id: "identity:alice", owner_account_id: "owner-1", left_handle: "local:alice", right_handle: "alice", relation: "same" as const, evidence_refs: ["e-1"], effective_at: 1, reversed_at: null };
const provisional = { claim_lineage_id: "lineage:p1", claim_revision_id: "p-1", owner_account_id: "owner-1", predicate: "preference", arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref" as const, ref: "entity:alice" } }], temporal_scope: { observed_at: "2026-01-02", precision: "day" }, evidence_refs: ["e-1"], policy_labels: [], source_language: "en", scope: { locality: "durable" as const, scope_ref: "entity:alice" }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: { version: "v1", referent_refs: [], topic_refs: [] } };
const canonical = { ...provisional, claim_lineage_id: "lineage:c1", claim_revision_id: "c-1", lifecycle: "canonical" as const, canonical_claim_id: "canonical:c1", source_provisional_revision_ids: ["p-1"] };

const transition = (idempotencyKey = "key-1", parentCommit: string | null = null): AtomicGraphTransition => {
  const derivation = prepareDerivation({ attempt_id: `attempt:${idempotencyKey}`, commit_id: `commit:${idempotencyKey}`, owner_account_id: "owner-1", parent_commit: parentCommit, idempotency_key: idempotencyKey, input_revisions: [{ revision_id: "p-1", content: provisional }], output_revisions: [{ revision_id: "c-1", content: canonical }, { revision_id: "entity:alice:r1", content: entity }, { revision_id: "identity:alice:r1", content: identity }], versions, success_kind: "success" });
  return { placement: { offline_experiment: true, allocations: { "p-1": "canonical:c1" }, results: [{ input_provisional_revision_id: "p-1", disposition: "admit", operation: { kind: "identity_linkage", entity_id: "entity:alice" } }] }, derivation, revisions: [{ kind: "claim", revision_id: "p-1", claim: provisional, placement_status: "consumed" }, { kind: "claim", revision_id: "c-1", claim: canonical, placement_status: "canonical" }, { kind: "entity", revision_id: "entity:alice:r1", entity }, { kind: "identity", revision_id: "identity:alice:r1", constraint: identity }], adjacency: [{ claim_revision_id: "c-1", entity_id: "entity:alice", role_slot_id: "subject" }] };
};

test("T9 atomically persists the T7 transition, ledger/head, and generated adjacency", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const plan = transition();
  expect(ledger.append(plan)).toEqual({ commit_id: "commit:key-1", sequence: 1, idempotent: false });
  expect(ledger.append(plan)).toEqual({ commit_id: "commit:key-1", sequence: 1, idempotent: true });
  const snapshot = ledger.snapshot("owner-1");
  expect(snapshot.claims.filter((item) => item.placement_status === "canonical")).toHaveLength(1);
  expect(snapshot.adjacency).toEqual([{ claim_revision_id: "c-1", entity_id: "entity:alice", role_slot_id: "subject" }]);
  expect(ledger.counts()).toMatchObject({ claim_revisions: 2, entity_revisions: 1, identity_revisions: 1, generated_adjacency: 1, consumed_markers: 1, derivation_attempts: 1, derivation_commits: 1, graph_heads: 1 });
});

test("T9 same key plus a different input/version digest is a hard conflict; equal content with another key is distinct", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  ledger.append(transition("key-1"));
  const changedVersions = { ...versions, code_version: "c2" };
  const conflicting = transition("key-1");
  const changed = { ...conflicting, derivation: prepareDerivation({ attempt_id: "attempt:conflict", commit_id: "commit:conflict", owner_account_id: "owner-1", parent_commit: "commit:key-1", idempotency_key: "key-1", input_revisions: [{ revision_id: "p-1", content: provisional }], output_revisions: [{ revision_id: "c-1", content: canonical }, { revision_id: "entity:alice:r1", content: entity }, { revision_id: "identity:alice:r1", content: identity }], versions: changedVersions, success_kind: "success" }) };
  expect(() => ledger.append(changed)).toThrow(IdempotencyConflictError);
  const empty = (key: string, parent_commit: string): AtomicGraphTransition => ({
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation: prepareDerivation({ attempt_id: `attempt:${key}`, commit_id: `commit:${key}`, owner_account_id: "owner-1", parent_commit, idempotency_key: key, input_revisions: [], output_revisions: [], versions, success_kind: "successful_empty" }),
    revisions: [], adjacency: [],
  });
  const independentA = empty("key-2", "commit:key-1");
  const independentB = empty("key-3", "commit:key-2");
  expect(independentA.derivation.commit.input_version_digest).toBe(independentB.derivation.commit.input_version_digest);
  expect(ledger.append(independentA)).toMatchObject({ commit_id: "commit:key-2", sequence: 2, idempotent: false });
  expect(ledger.append(independentB)).toMatchObject({ commit_id: "commit:key-3", sequence: 3, idempotent: false });
});

test("T9 injected crash rolls back every write; committed active claims remain traversable", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  expect(() => ledger.append(transition(), "after_adjacency")).toThrow("injected crash");
  expect(ledger.counts()).toEqual({ claim_revisions: 0, entity_revisions: 0, identity_revisions: 0, event_revisions: 0, evidence_revisions: 0, generated_adjacency: 0, consumed_markers: 0, derivation_attempts: 0, derivation_commits: 0, graph_heads: 0 });
  ledger.append(transition());
  const snapshot = ledger.snapshot("owner-1");
  for (const claim of snapshot.claims.filter((item) => item.placement_status === "canonical")) expect(snapshot.adjacency.some((edge) => edge.claim_revision_id === claim.revision_id)).toBe(true);
});

test("T10 SQLite entity retrieval keeps withheld claims in omission accounting, not returned content", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const withheld = { ...provisional, claim_revision_id: "p-unresolved", claim_lineage_id: "lineage:unresolved", arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal" as const, value: "He" } }], ambiguity_markers: ["unresolved_subject"] };
  const derivation = prepareDerivation({ attempt_id: "attempt:withheld", commit_id: "commit:withheld", owner_account_id: "owner-1", parent_commit: null, idempotency_key: "key-withheld", input_revisions: [{ revision_id: "p-unresolved", content: withheld }], output_revisions: [], versions, success_kind: "successful_empty" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [{ input_provisional_revision_id: "p-unresolved", disposition: "defer_review", operation: null, re_resolution_trigger: "new_identity_evidence" }] }, derivation, revisions: [{ kind: "claim", revision_id: "p-unresolved", claim: withheld, placement_status: "withheld_unresolved_subject" }], adjacency: [] });
  const result = ledger.retrieve({ owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" });
  expect(result.claims).toEqual([]);
  expect(result.omission_accounting).toMatchObject({ returned_canonical: 0, withheld_items: 1, omitted_items: 1 });
});

test("T9 SQLite round-trips claim evidence through Evidence, Event, Capture, and excerpt", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  ledger.append(transition());
  const event = { event_id: "event:e1", event_revision_id: "event:e1:r1", owner_account_id: "owner-1", capture_session_id: "capture:roundtrip", stream_id: "stream:roundtrip", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-02", ingest_time: "2026-01-02", source_sequence: 7, evidence_addressable_refs: ["e-1"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "event-hash" };
  const evidence = { evidence_id: "e-1", event_revision_id: "event:e1:r1", source_unit_ref: "unit:1", range: { start: 4, end: 15 }, excerpt: "roundtrip span", source_local_speaker_ref: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture:roundtrip" };
  const derivation = prepareDerivation({ attempt_id: "attempt:evidence", commit_id: "commit:evidence", owner_account_id: "owner-1", parent_commit: "commit:key-1", idempotency_key: "key-evidence", input_revisions: [], output_revisions: [{ revision_id: "event:e1:r1", content: event }, { revision_id: "e-1:r1", content: evidence }], versions, success_kind: "success" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions: [{ kind: "event", revision_id: "event:e1:r1", event }, { kind: "evidence", revision_id: "e-1:r1", evidence }], adjacency: [] });
  const projected = projectTreeInputSnapshot(ledger.snapshot("owner-1"), { account_timezone: "UTC" });
  expect(projected.claims.find((claim) => claim.claim_revision_id === "c-1")?.evidence_spans).toEqual([expect.objectContaining({ evidence_id: "e-1", event_revision_id: "event:e1:r1", capture_session_id: "capture:roundtrip", excerpt: "roundtrip span", range: { start: 4, end: 15 } })]);
  expect(projected.diagnostics).toEqual([]);
});
