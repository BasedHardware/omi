import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { liveCommittedClaims } from "../../core/retrieve";
import type { ProvisionalClaim } from "../../core/schema";
import { predicateIdForName } from "../../core/consolidate/predicate-identity";
import { SqliteLedger } from "../sqlite";
import { DeterministicFakeModel } from "./port";
import { commitSessionStmToLtmTransition, planSessionStmToLtmTransition } from "./stm-ltm-transition";

test("I1 commits event and evidence with a session transition so later claims are live", async () => {
  const identity = { namespace_instance_ref: "device", local_key: "owner", producer: { producer_ref: "producer", contract_ref: "contract" }, asserted_identity: { domain: "person", scope_ref: "owner" } };
  const authorization = { authorization_id: "a", owner_account_id: "owner", endpoints: [{ kind: "source_identity" as const, source_identity_ref: identity }, { kind: "entity" as const, entity_id: "entity:owner" }], relation: "same" as const, support: { kind: "owner_confirmation" as const, confirmation_ref: "confirm" }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: "device", identity_domain: "person", scope_ref: "owner" }, authority_policy_version: "v1", evaluated_frontier: 0, actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active" as const, superseded_by: null };
  const claim: ProvisionalClaim = { claim_lineage_id: "l", claim_revision_id: "p", owner_account_id: "owner", predicate_id: predicateIdForName("met"), predicate: "met", arguments: [{ slot_id: "speaker", role: "speaker", surface: "I", span: { start: 0, end: 1 }, value: { kind: "source_local_ref", ref: "speaker:0" } }], observed_speaker_slot_id: "speaker", polarity: "positive", temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: ["e"], policy_labels: [], source_language: "en", scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers: [], context_packet: null };
  const event = { event_id: "event", event_revision_id: "event:r1", owner_account_id: "owner", capture_session_id: "session", stream_id: "stream", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:00Z", ingest_time: "2026-01-01T00:00:00Z", source_sequence: 0, evidence_addressable_refs: ["e"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "hash" };
  const evidence = [{ evidence_id: "e", event_revision_id: "event:r1", source_unit_ref: "u", range: { start: 0, end: 10 }, excerpt: "I met Alice", source_identity_ref: identity, speaker_rendering: "Owner", source_local_mention_ref: "speaker-0", state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture" }];
  const model = new DeterministicFakeModel((request) => request.strategy === "mention-local-handle" ? { mentions: [{ claim_revision_id: "p", slot_id: "speaker", surface: "I", evidence_id: "e", antecedent_handle: null }] } : request.strategy === "local-handle-durable-entity" ? { decision: "same", entity_id: "entity:owner" } : request.strategy === "scope-role-binding" ? { bindings: { speaker: "entity:owner" }, scope: { locality: "durable", scope_ref: "global" } } : { decision: "accept_ltm" });
  const ledger = new SqliteLedger(new Database(":memory:"));
  const request = { ledger, model, session_id: "session", formation_work_id: "work:session:event:v1", owner_account_id: "owner", graph_frontier: 0, provisionals: [claim], entities: [{ entity_id: "entity:owner", owner_account_id: "owner", entity_revision_id: "entity:owner:r1", handle: "owner", labels: ["Owner"] }], evidence, events: [event], valid_times: { p: { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-01-01T00:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-01-01T00:00:00Z", end: "2026-01-01T00:00:00Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } } }, parent_commit: null, versions: { strategy_version: "test", model_version: "fake", prompt_version: "test", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "test", tool_version: "test" }, identity_authorizations: [authorization], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirm", owner_account_id: "owner", endpoints: authorization.endpoints, relation: "same" as const }], producer_assertions: [], standing_policies: [] } };
  const { ledger: _ledger, ...planning } = request;
  const planned = await planSessionStmToLtmTransition(planning);
  expect(planned.revisions.some((revision) => revision.kind === "claim" && revision.placement_status === "canonical")).toBe(true);
  expect(ledger.snapshot("owner").claims).toEqual([]);
  await commitSessionStmToLtmTransition(request);
  await expect(commitSessionStmToLtmTransition({ ...request, identity_authorizations: [] })).rejects.toThrow("formation work id reused with changed input or versions");
  await expect(commitSessionStmToLtmTransition({ ...request, identity_authority_context: { owner_confirmations: [], producer_assertions: [], standing_policies: [] } })).rejects.toThrow("formation work id reused with changed input or versions");
  const snapshot = ledger.snapshot("owner");
  expect(snapshot.evidence?.map((item) => item.evidence.evidence_id)).toEqual(["e"]);
  expect(snapshot.predicates?.map((item) => item.predicate)).toEqual([
    expect.objectContaining({ predicate_id: predicateIdForName("met"), identity_version: "name-v2", slot_ids: [], observed_roles: ["speaker"] }),
  ]);
  expect(liveCommittedClaims(snapshot).filter((item) => item.claim.lifecycle === "canonical")).toHaveLength(1);

  const legacyLedger = new SqliteLedger(new Database(":memory:"));
  const legacyClaim = { ...claim, predicate_id: "predicate:legacy-name-plus-window-slots" };
  await commitSessionStmToLtmTransition({
    ...request,
    ledger: legacyLedger,
    formation_work_id: "work:session:event:legacy-v1",
    provisionals: [legacyClaim],
  });
  expect(legacyLedger.snapshot("owner").predicates?.map((item) => item.predicate)).toEqual([
    expect.objectContaining({
      predicate_id: "predicate:legacy-name-plus-window-slots",
      identity_version: "name-slots-v1",
      slot_ids: ["speaker"],
    }),
  ]);
});

test("D44 an anaphor binds through its antecedent, which a per-evidence handle key made unreachable", async () => {
  // Two speakers, one discourse unit. Only the FIRST has a typed authorization,
  // so "She" can reach `entity:alice` through its antecedent or not at all --
  // which is exactly what makes this test detect the collapsed key. Keying local
  // handles per evidence gave every slot in a segment one handle, and none of
  // them was the `local:<mention_id>` that extraction emits as an antecedent.
  const speakerA = { namespace_instance_ref: "device", local_key: "channel-a", producer: { producer_ref: "producer", contract_ref: "contract" }, asserted_identity: { domain: "person", scope_ref: "owner" } };
  const speakerB = { ...speakerA, local_key: "channel-b" };
  const authorization = { authorization_id: "a", owner_account_id: "owner", endpoints: [{ kind: "source_identity" as const, source_identity_ref: speakerA }, { kind: "entity" as const, entity_id: "entity:alice" }], relation: "same" as const, support: { kind: "owner_confirmation" as const, confirmation_ref: "confirm" }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: "device", identity_domain: "person", scope_ref: "owner" }, authority_policy_version: "v1", evaluated_frontier: 0, actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active" as const, superseded_by: null };
  const provisional = (revision: string, predicate: string, surface: string, evidence_id: string, speakerSlot: string | null): ProvisionalClaim => ({ claim_lineage_id: `l:${revision}`, claim_revision_id: revision, owner_account_id: "owner", predicate, arguments: [{ slot_id: "subject", role: "subject", surface, span: { start: 0, end: surface.length }, value: { kind: "source_local_ref", ref: `source-local:${evidence_id}` } }], observed_speaker_slot_id: speakerSlot, polarity: "positive", temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: [evidence_id], policy_labels: [], source_language: "en", scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers: [], context_packet: null });
  const named = provisional("p1", "arrived", "Alice", "e-alice", "subject");
  const anaphor = provisional("p2", "laughed", "She", "e-she", null);
  const events = [
    { event_id: "ev-alice", event_revision_id: "event:alice", owner_account_id: "owner", capture_session_id: "session", stream_id: "stream", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:00Z", ingest_time: null, source_sequence: 0, evidence_addressable_refs: ["e-alice"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "hash-a" },
    { event_id: "ev-she", event_revision_id: "event:she", owner_account_id: "owner", capture_session_id: "session", stream_id: "stream", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:01Z", ingest_time: null, source_sequence: 1, evidence_addressable_refs: ["e-she"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "hash-b" },
  ];
  // One `source_unit_ref` is what keeps the link source-local: an antecedent can
  // never reach across discourse units.
  const evidence = [
    { evidence_id: "e-alice", event_revision_id: "event:alice", source_unit_ref: "u", range: { start: 0, end: 14 }, excerpt: "Alice arrived.", source_identity_ref: speakerA, speaker_rendering: "Alice", source_local_mention_ref: "alice-0", state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture-a" },
    { evidence_id: "e-she", event_revision_id: "event:she", source_unit_ref: "u", range: { start: 0, end: 12 }, excerpt: "She laughed.", source_identity_ref: speakerB, speaker_rendering: null, source_local_mention_ref: "she-0", state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture-b" },
  ];
  const model = new DeterministicFakeModel((request) => request.strategy === "mention-local-handle"
    ? { mentions: [
      { claim_revision_id: "p1", slot_id: "subject", surface: "Alice", evidence_id: "e-alice", antecedent_handle: null },
      { claim_revision_id: "p2", slot_id: "subject", surface: "She", evidence_id: "e-she", antecedent_handle: "local:mention:p1:subject" },
    ] }
    : request.strategy === "local-handle-durable-entity" ? { decision: "same", entity_id: "entity:alice" }
    : request.strategy === "scope-role-binding" ? { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "global" } }
    : { decision: "accept_ltm" });
  const validTime = { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-01-01T00:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-01-01T00:00:00Z", end: "2026-01-01T00:00:00Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } };
  const ledger = new SqliteLedger(new Database(":memory:"));
  await commitSessionStmToLtmTransition({ ledger, model, session_id: "session", formation_work_id: "work:session:anaphor:v1", owner_account_id: "owner", graph_frontier: 0, provisionals: [named, anaphor], entities: [{ entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] }], evidence, events, valid_times: { p1: validTime, p2: validTime }, parent_commit: null, versions: { strategy_version: "test", model_version: "fake", prompt_version: "test", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "test", tool_version: "test" }, identity_authorizations: [authorization], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirm", owner_account_id: "owner", endpoints: authorization.endpoints, relation: "same" }], producer_assertions: [], standing_policies: [] } });

  const snapshot = ledger.snapshot("owner");
  const mentions = (snapshot.mentions ?? []).map((item) => item.mention);
  const she = mentions.find((mention) => mention.mention_id === "mention:p2:subject")!;
  expect(she.antecedent_handle).toBe("local:mention:p1:subject");
  expect(she).toMatchObject({ resolution: "resolved", entity_id: "entity:alice" });
  // Both claims are durably placed, and the anaphor's subject really is bound.
  const canonical = liveCommittedClaims(snapshot).filter((item) => item.claim.lifecycle === "canonical");
  expect(canonical).toHaveLength(2);
  expect(snapshot.adjacency.filter((edge) => edge.entity_id === "entity:alice")).toHaveLength(2);
});

test("P1 a missing or repaired speaker slot can never reload evidence-wide owner authority", async () => {
  const ownerIdentity = { namespace_instance_ref: "device", local_key: "owner", producer: { producer_ref: "producer", contract_ref: "contract" }, asserted_identity: { domain: "person", scope_ref: "owner" } };
  const authorization = { authorization_id: "owner-auth", owner_account_id: "owner", endpoints: [{ kind: "source_identity" as const, source_identity_ref: ownerIdentity }, { kind: "entity" as const, entity_id: "entity:owner" }], relation: "same" as const, support: { kind: "owner_confirmation" as const, confirmation_ref: "confirm-owner" }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: "device", identity_domain: "person", scope_ref: "owner" }, authority_policy_version: "v1", evaluated_frontier: 0, actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active" as const, superseded_by: null };
  const claim: ProvisionalClaim = {
    claim_lineage_id: "lineage:repaired-speaker", claim_revision_id: "p-repaired", owner_account_id: "owner", predicate: "named",
    arguments: [{ slot_id: "subject", role: "subject", surface: "I", span: { start: 0, end: 1 }, value: { kind: "source_local_ref", ref: "source-local:e:0:1" } }],
    observed_speaker_slot_id: null, polarity: "positive", temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: ["e-repaired"], policy_labels: [], source_language: "en", scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers: ["repaired:speaker_slot_annotation_dropped"], context_packet: null,
  };
  const event = { event_id: "event-repaired", event_revision_id: "event:repaired", owner_account_id: "owner", capture_session_id: "session-repaired", stream_id: "stream", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:00Z", ingest_time: "2026-01-01T00:00:00Z", source_sequence: 0, evidence_addressable_refs: ["e-repaired"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "hash-repaired" };
  const evidence = [{ evidence_id: "e-repaired", event_revision_id: "event:repaired", source_unit_ref: "unit:repaired", range: { start: 0, end: 9 }, excerpt: "I am Nora", source_identity_ref: ownerIdentity, speaker_rendering: "Owner", source_local_mention_ref: "owner-0", state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture-repaired" }];
  const model = new DeterministicFakeModel((request) => request.strategy === "mention-local-handle"
    ? { mentions: [{ claim_revision_id: "p-repaired", slot_id: "subject", surface: "I", evidence_id: "e-repaired", antecedent_handle: null }] }
    : request.strategy === "local-handle-durable-entity" ? { decision: "same", entity_id: "entity:owner" }
    : request.strategy === "scope-role-binding" ? { bindings: { subject: "entity:owner" }, scope: { locality: "durable", scope_ref: "global" } }
    : { decision: "accept_ltm" });
  const ledger = new SqliteLedger(new Database(":memory:"));
  const validTime = { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-01-01T00:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-01-01T00:00:00Z", end: "2026-01-01T00:00:00Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } };
  await commitSessionStmToLtmTransition({ ledger, model, session_id: "session-repaired", formation_work_id: "work:session-repaired:v1", owner_account_id: "owner", graph_frontier: 0, provisionals: [claim], entities: [{ entity_id: "entity:owner", owner_account_id: "owner", entity_revision_id: "entity:owner:r1", handle: "owner", labels: ["Owner"] }], evidence, events: [event], valid_times: { "p-repaired": validTime }, parent_commit: null, versions: { strategy_version: "test", model_version: "fake", prompt_version: "test", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "test", tool_version: "test" }, identity_authorizations: [authorization], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirm-owner", owner_account_id: "owner", endpoints: authorization.endpoints, relation: "same" }], producer_assertions: [], standing_policies: [] } });

  const snapshot = ledger.snapshot("owner");
  const mention = snapshot.mentions?.find((item) => item.mention.claim_revision_id === "p-repaired")?.mention;
  expect(mention).toMatchObject({ resolution: "unresolved", entity_id: null, source_identity_ref: { namespace_instance_ref: "source-local:e-repaired", producer: { producer_ref: null, contract_ref: null } } });
  expect(liveCommittedClaims(snapshot).filter((item) => item.claim.lifecycle === "canonical")).toHaveLength(0);
  expect(snapshot.adjacency.some((edge) => edge.entity_id === "entity:owner")).toBe(false);
  expect(snapshot.identity_constraints ?? []).toEqual([]);
});
