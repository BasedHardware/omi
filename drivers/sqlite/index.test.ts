import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { prepareDerivation, validateAtomicGraphTransition, type AtomicGraphTransition, type DerivationVersions } from "../../core/ledger";
import { persistValidTime, project, projectTreeInputSnapshot } from "../../core/retrieve";
import { retrieveDogfood } from "../../core/retrieve/dogfood";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";
import { IdempotencyConflictError, SqliteLedger } from "./index";

const versions: DerivationVersions = { strategy_version: "placement-v1", model_version: "none", prompt_version: "none", policy_version: "p1", code_version: "c1", schema_version: "s1", tokenizer_version: "none", tool_version: "none" };
const entity = { entity_id: "entity:alice", owner_account_id: "owner-1", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] };
const sourceIdentity = { namespace_instance_ref: "namespace:test", local_key: "alice", producer: { producer_ref: null, contract_ref: null }, asserted_identity: { domain: null, scope_ref: null } };
const authorization = { authorization_id: "authorization:alice", owner_account_id: "owner-1", endpoints: [{ kind: "source_identity" as const, source_identity_ref: sourceIdentity }, { kind: "entity" as const, entity_id: "entity:alice" }], relation: "same" as const, support: { kind: "owner_confirmation" as const, confirmation_ref: "confirmation:alice" }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: "namespace:test", identity_domain: null, scope_ref: null }, authority_policy_version: "identity-policy:v1", evaluated_frontier: 1, actor_provenance: { actor_ref: "owner-1", producer_ref: null }, lifecycle: "active" as const, superseded_by: null };
const identity = { constraint_id: "identity:alice", owner_account_id: "owner-1", endpoints: authorization.endpoints, left_handle: "legacy:local:alice", right_handle: "legacy:alice", relation: "same" as const, evidence_refs: ["e-1"], identity_authorization: authorization, effective_at: 1, reversed_at: null };
const provisional = { claim_lineage_id: "lineage:p1", claim_revision_id: "p-1", owner_account_id: "owner-1", predicate: "preference", arguments: [{ slot_id: "subject", role: "subject", value: { kind: "entity_ref" as const, ref: "entity:alice" } }], temporal_scope: { observed_at: "2026-01-02", precision: "day" }, evidence_refs: ["e-1"], policy_labels: [], source_language: "en", scope: { locality: "durable" as const, scope_ref: "entity:alice" }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: { version: "v1", referent_refs: [], topic_refs: [] } };
const canonical = { ...provisional, claim_lineage_id: "lineage:c1", claim_revision_id: "c-1", temporal_scope: { observed_at: "2026-01-02", precision: "day", valid_time: { typed_expression: { kind: "absolute" as const, granularity: "year" as const, value: "2026" }, resolved_interval: { kind: "calendar_interval" as const, start: "2026-01-01T00:00:00.000Z", end: "2027-01-01T00:00:00.000Z", timezone: "UTC", granularity: "year" as const }, derivation: { resolver_version: "g0-v1", timezone: "UTC" } } }, lifecycle: "canonical" as const, canonical_claim_id: "canonical:c1", source_provisional_revision_ids: ["p-1"] };
delete (canonical as { ambiguity_markers?: unknown }).ambiguity_markers;
delete (canonical as { context_packet?: unknown }).context_packet;

const transition = (idempotencyKey = "key-1", parentCommit: string | null = null): AtomicGraphTransition => {
  const derivation = prepareDerivation({ attempt_id: `attempt:${idempotencyKey}`, commit_id: `commit:${idempotencyKey}`, owner_account_id: "owner-1", parent_commit: parentCommit, idempotency_key: idempotencyKey, input_revisions: [{ revision_id: "p-1", content: provisional }], output_revisions: [{ revision_id: "c-1", content: canonical }, { revision_id: "entity:alice:r1", content: entity }, { revision_id: "identity:alice:r1", content: identity }], versions, success_kind: "success" });
  return { placement: { offline_experiment: true, allocations: { "p-1": "canonical:c1" }, results: [{ input_provisional_revision_id: "p-1", disposition: "admit", operation: { kind: "identity_linkage", entity_id: "entity:alice" } }] }, derivation, revisions: [{ kind: "claim", revision_id: "p-1", claim: provisional, placement_status: "consumed" }, { kind: "claim", revision_id: "c-1", claim: canonical, placement_status: "canonical" }, { kind: "mention", revision_id: "mention:m-alice", mention: { mention_id: "m-alice", owner_account_id: "owner-1", claim_revision_id: "p-1", span: { start: 0, end: 5 }, evidence_id: "e-1", source_identity_ref: sourceIdentity, speaker_rendering: "Alice", slot_id: "subject", surface: "Alice", antecedent_handle: null, resolution: "resolved", entity_id: "entity:alice" } }, { kind: "identity_authorization", revision_id: "identity-authorization:alice", authorization }, { kind: "entity", revision_id: "entity:alice:r1", entity }, { kind: "identity", revision_id: "identity:alice:r1", constraint: identity }], adjacency: [{ claim_revision_id: "c-1", entity_id: "entity:alice", role_slot_id: "subject" }], artifacts: [{ artifact_id: "auto-placement:p-1", kind: "auto_placement_log", provisional_revision_id: "p-1", canonical_claim_revision_id: "c-1", margin: "high", risk_markers: [], unit_boundary_decision: "accept_ltm", scope_locality: "durable" }], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirmation:alice", owner_account_id: "owner-1", endpoints: authorization.endpoints, relation: "same" }], producer_assertions: [], standing_policies: [] } };
};

test("T9 atomically persists the T7 transition, ledger/head, and generated adjacency", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const plan = transition();
  expect(ledger.append(plan)).toEqual({ commit_id: "commit:key-1", sequence: 1, idempotent: false });
  expect(ledger.append(plan)).toEqual({ commit_id: "commit:key-1", sequence: 1, idempotent: true });
  const snapshot = ledger.snapshot("owner-1");
  expect(snapshot.claims.filter((item) => item.placement_status === "canonical")).toHaveLength(1);
  expect(snapshot.adjacency).toEqual([{ claim_revision_id: "c-1", entity_id: "entity:alice", role_slot_id: "subject" }]);
  expect(snapshot.identity_constraints?.[0]?.constraint.identity_authorization).toEqual(identity.identity_authorization);
  expect(ledger.counts()).toMatchObject({ claim_revisions: 2, entity_revisions: 1, identity_revisions: 1, mention_revisions: 1, identity_authorization_revisions: 1, generated_adjacency: 1, consumed_markers: 1, derivation_attempts: 1, derivation_commits: 1, graph_heads: 1 });
});

test("S1 ledger transition commits require artifacts for every consumed provisional and direct canonical seeds cannot bypass identity authority", async () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const consumingWithoutArtifacts = { ...transition(), artifacts: [] };
  await expect(ledger.appendTransitionPlan(consumingWithoutArtifacts)).rejects.toThrow("provisional-consuming transition requires placement artifacts covering provisional: p-1");

  const seed = { ...canonical, claim_revision_id: "c-seed", claim_lineage_id: "lineage:seed", canonical_claim_id: "canonical:seed", source_provisional_revision_ids: [] };
  const seedDerivation = prepareDerivation({ attempt_id: "attempt:seed", commit_id: "commit:seed", owner_account_id: "owner-1", parent_commit: null, idempotency_key: "seed", input_revisions: [], output_revisions: [{ revision_id: "c-seed", content: seed }], versions, success_kind: "success" });
  await expect(ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation: seedDerivation, revisions: [{ kind: "claim", revision_id: "c-seed", claim: seed, placement_status: "canonical" }], adjacency: [{ claim_revision_id: "c-seed", entity_id: "entity:alice", role_slot_id: "subject" }], artifacts: [] })).rejects.toThrow("durable role binding lacks typed mention lineage");
});

test("D41 adversarial public ledger validator rejects a provisional in both queue and abstention strata", () => {
  const invalid = transition();
  invalid.artifacts = [...invalid.artifacts, { ...invalid.artifacts[0]!, artifact_id: "abstention-set:p-1", kind: "abstention_set", canonical_claim_revision_id: null, unit_boundary_decision: "abstain" }];
  expect(() => validateAtomicGraphTransition(invalid)).toThrow("exactly one placement artifact: p-1");
});

test("I6 adversarial direct ledger plans cannot bypass identity coverage", () => {
  const noAuthorization = transition();
  noAuthorization.revisions = noAuthorization.revisions.filter((revision) => revision.kind !== "identity_authorization");
  expect(() => validateAtomicGraphTransition(noAuthorization)).toThrow("identity constraint lacks persisted authorization");

  const wrongEntity = transition();
  wrongEntity.revisions = wrongEntity.revisions.map((revision) => revision.kind === "claim" && revision.revision_id === "c-1"
    ? { ...revision, claim: { ...revision.claim, arguments: [{ ...revision.claim.arguments[0]!, value: { kind: "entity_ref" as const, ref: "entity:bob" } }] } }
    : revision.kind === "mention" ? { ...revision, mention: { ...revision.mention, entity_id: "entity:bob" } } : revision);
  wrongEntity.adjacency = [{ claim_revision_id: "c-1", entity_id: "entity:bob", role_slot_id: "subject" }];
  expect(() => validateAtomicGraphTransition(wrongEntity)).toThrow("durable role binding lacks identity authorization");

  const wrongRelation = transition();
  wrongRelation.revisions = wrongRelation.revisions.map((revision) => revision.kind === "identity" ? { ...revision, constraint: { ...revision.constraint, relation: "distinct" as const } } : revision);
  expect(() => validateAtomicGraphTransition(wrongRelation)).toThrow("invalid identity constraint authorization");

  const unconsumed = transition();
  unconsumed.revisions = unconsumed.revisions.filter((revision) => revision.kind !== "claim" && revision.kind !== "mention" && revision.kind !== "identity");
  unconsumed.adjacency = [];
  unconsumed.placement = { offline_experiment: true, allocations: {}, results: [] };
  unconsumed.artifacts = [];
  expect(() => validateAtomicGraphTransition(unconsumed)).toThrow("identity authorization has no dependent binding");
});

test("E2 rejects fabricated consolidation support whose evidence and claim lineage do not exist", () => {
  const forged = transition("e2:forged-support");
  const auth = { ...authorization, authorization_id: "authorization:e2", support: { kind: "consolidation_adjudication" as const, support_refs: ["support:forged", "support:forged:second"], proposal_lineage_ref: "proposal:forged" } };
  forged.revisions = forged.revisions.map((revision) => revision.kind === "identity_authorization" ? { ...revision, authorization: auth }
    : revision.kind === "identity" ? { ...revision, constraint: { ...revision.constraint, identity_authorization: auth } } : revision);
  forged.identity_authority_context = { owner_confirmations: [], producer_assertions: [], standing_policies: [], identity_support: [{ support_ref: "support:forged", owner_account_id: "owner-1", evidence_ref: "evidence:does-not-exist", claim_revision_id: "claim:does-not-exist", source_independence_key: "root:forged" }, { support_ref: "support:forged:second", owner_account_id: "owner-1", evidence_ref: "evidence:also-does-not-exist", claim_revision_id: "claim:does-not-exist", source_independence_key: "root:forged:second" }] };
  expect(() => validateAtomicGraphTransition(forged)).toThrow("unresolvable identity support lineage");
});

test("E3 persists consolidation support atomically and retains it across rebuild", () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const plan = transition("e3:durable-support");
  const auth = { ...authorization, authorization_id: "authorization:e3", support: { kind: "consolidation_adjudication" as const, support_refs: ["support:e3", "support:e3:second"], proposal_lineage_ref: "proposal:e3" } };
  const event = { event_id: "event:e3", event_revision_id: "event:e3:r1", owner_account_id: "owner-1", capture_session_id: "capture:e3", stream_id: "stream:e3", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-01", ingest_time: "2026-01-01", source_sequence: 1, evidence_addressable_refs: ["evidence:e3"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "event:e3" };
  const evidence = { evidence_id: "evidence:e3", event_revision_id: "event:e3:r1", source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: "synthetic", source_identity_ref: sourceIdentity, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "root:e3" };
  const eventSecond = { ...event, event_id: "event:e3:second", event_revision_id: "event:e3:second:r1", capture_session_id: "capture:e3:second", canonical_redacted_hash: "event:e3:second" };
  const evidenceSecond = { ...evidence, evidence_id: "evidence:e3:second", event_revision_id: eventSecond.event_revision_id, source_independence_key: "root:e3:second" };
  plan.revisions = plan.revisions.map((revision) => revision.kind === "identity_authorization" ? { ...revision, authorization: auth }
    : revision.kind === "identity" ? { ...revision, constraint: { ...revision.constraint, identity_authorization: auth } } : revision)
    .concat([{ kind: "event" as const, revision_id: "event:e3:r1", event }, { kind: "evidence" as const, revision_id: "evidence:e3:r1", evidence }, { kind: "event" as const, revision_id: eventSecond.event_revision_id, event: eventSecond }, { kind: "evidence" as const, revision_id: "evidence:e3:second:r1", evidence: evidenceSecond }]);
  plan.identity_authority_context = { owner_confirmations: [], producer_assertions: [], standing_policies: [] };
  // Support reaches the validator only through the TRUSTED derived channel; a
  // caller-supplied origin is rejected outright, and an absent one now fails closed.
  plan.derived_identity_support = [{ support_ref: "support:e3", owner_account_id: "owner-1", evidence_ref: "evidence:e3", claim_revision_id: "c-1", source_independence_key: "root:e3", support_origin: "independent" as const }, { support_ref: "support:e3:second", owner_account_id: "owner-1", evidence_ref: "evidence:e3:second", claim_revision_id: "c-1", source_independence_key: "root:e3:second", support_origin: "independent" as const }];
  ledger.append(plan);
  expect(ledger.counts()).toMatchObject({ identity_support_revisions: 2 });
  const rebuilt = new SqliteLedger(db);
  expect(rebuilt.counts()).toMatchObject({ identity_support_revisions: 2 });
  expect(rebuilt.auditIdentityAuthority("owner-1")).toEqual({ authorizations: 1, supports: 2 });
});

test("E5 rejects a later dream same when durable active constraints contain owner distinct", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const distinct = transition("e5:owner-distinct");
  const distinctAuth = { ...authorization, authorization_id: "authorization:e5:distinct", relation: "distinct" as const };
  distinct.placement = { offline_experiment: true, allocations: {}, results: [] };
  distinct.artifacts = []; distinct.adjacency = [];
  distinct.revisions = distinct.revisions.filter((revision) => revision.kind === "identity_authorization" || revision.kind === "identity").map((revision) => revision.kind === "identity_authorization" ? { ...revision, authorization: distinctAuth } : { ...revision, constraint: { ...revision.constraint, relation: "distinct" as const, identity_authorization: distinctAuth } });
  distinct.identity_authority_context = { owner_confirmations: [{ confirmation_ref: "confirmation:alice", owner_account_id: "owner-1", endpoints: distinctAuth.endpoints, relation: "distinct" }], producer_assertions: [], standing_policies: [] };
  ledger.append(distinct);

  const dream = transition("e5:dream-same", "commit:e5:owner-distinct");
  const dreamAuth = { ...authorization, authorization_id: "authorization:e5:dream", support: { kind: "consolidation_adjudication" as const, support_refs: ["support:e5", "support:e5:second"], proposal_lineage_ref: "proposal:e5" } };
  const event = { event_id: "event:e5", event_revision_id: "event:e5:r1", owner_account_id: "owner-1", capture_session_id: "capture:e5", stream_id: "stream:e5", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-01", ingest_time: "2026-01-01", source_sequence: 1, evidence_addressable_refs: ["evidence:e5"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "event:e5" };
  const evidence = { evidence_id: "evidence:e5", event_revision_id: "event:e5:r1", source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: "synthetic", source_identity_ref: sourceIdentity, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "root:e5" };
  const eventSecond = { ...event, event_id: "event:e5:second", event_revision_id: "event:e5:second:r1", capture_session_id: "capture:e5:second", canonical_redacted_hash: "event:e5:second" };
  const evidenceSecond = { ...evidence, evidence_id: "evidence:e5:second", event_revision_id: eventSecond.event_revision_id, source_independence_key: "root:e5:second" };
  const lineageClaim = { ...canonical, claim_revision_id: "c-e5", claim_lineage_id: "lineage:e5", canonical_claim_id: "canonical:e5", source_provisional_revision_ids: [], evidence_refs: ["evidence:e5"], arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal" as const, value: "synthetic" } }] };
  dream.placement = { offline_experiment: true, allocations: {}, results: [] }; dream.artifacts = []; dream.adjacency = [];
  dream.revisions = [{ kind: "identity_authorization", revision_id: "identity-authorization:e5", authorization: dreamAuth }, { kind: "identity", revision_id: "identity:e5", constraint: { ...identity, constraint_id: "identity:e5", identity_authorization: dreamAuth } }, { kind: "claim", revision_id: "c-e5", claim: lineageClaim, placement_status: "canonical" }, { kind: "event", revision_id: "event:e5:r1", event }, { kind: "evidence", revision_id: "evidence:e5:r1", evidence }, { kind: "event", revision_id: eventSecond.event_revision_id, event: eventSecond }, { kind: "evidence", revision_id: "evidence:e5:second:r1", evidence: evidenceSecond }];
  dream.identity_authority_context = { owner_confirmations: [], producer_assertions: [], standing_policies: [] };
  // Support reaches the validator only through the TRUSTED derived channel; a
  // caller-supplied origin is rejected outright, and an absent one now fails closed.
  dream.derived_identity_support = [{ support_ref: "support:e5", owner_account_id: "owner-1", evidence_ref: "evidence:e5", claim_revision_id: "c-e5", source_independence_key: "root:e5", support_origin: "independent" as const }, { support_ref: "support:e5:second", owner_account_id: "owner-1", evidence_ref: "evidence:e5:second", claim_revision_id: "c-e5", source_independence_key: "root:e5:second", support_origin: "independent" as const }];
  expect(() => ledger.append(dream)).toThrow("durable active identity conflict");
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
    revisions: [], adjacency: [], artifacts: [],
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
  expect(ledger.counts()).toEqual({ claim_revisions: 0, entity_revisions: 0, identity_revisions: 0, event_revisions: 0, evidence_revisions: 0, mention_revisions: 0, identity_authorization_revisions: 0, identity_support_revisions: 0, coreference_support_revisions: 0, candidate_derivation_artifacts: 0, generated_adjacency: 0, consumed_markers: 0, placement_artifacts: 0, derivation_attempts: 0, derivation_commits: 0, graph_heads: 0, claim_liveness_fences: 0, identity_quarantine_records: 0, claim_quarantine_records: 0 });
  ledger.append(transition());
  const snapshot = ledger.snapshot("owner-1");
  for (const claim of snapshot.claims.filter((item) => item.placement_status === "canonical")) expect(snapshot.adjacency.some((edge) => edge.claim_revision_id === claim.revision_id)).toBe(true);
});

test("I7 persists authorization/constraint parents atomically, heads identity revisions by commit sequence, and repairs through the append validator", async () => {
  const db = new Database(":memory:");
  const ledger = new SqliteLedger(db);
  // The relationship is database-enforced, independently of the TypeScript API.
  expect(() => db.query("INSERT INTO identity_revisions (revision_id, owner_account_id, content_json, content_hash, commit_id, constraint_id, authorization_revision_id) VALUES (?, ?, ?, ?, ?, ?, ?)").run("raw:identity", "owner-1", "{}", "h", "missing:commit", "raw:constraint", "missing:authorization")).toThrow();

  for (const crashAt of ["after_authorization", "after_constraint", "after_adjacency"] as const) {
    expect(() => ledger.append(transition(`crash:${crashAt}`), crashAt)).toThrow("injected crash");
    expect(Object.values(ledger.counts()).every((count) => count === 0)).toBe(true);
  }

  const committed = transition("identity:head");
  expect(await ledger.replayTransitionPlan(committed)).toMatchObject({ idempotent: false, sequence: 1 });
  // Historical replay is idempotent but validation is still run before the lookup.
  const invalidReplay = transition("identity:invalid", "commit:identity:head");
  invalidReplay.revisions = invalidReplay.revisions.filter((revision) => revision.kind !== "identity_authorization");
  await expect(ledger.repairTransitionPlan(invalidReplay)).rejects.toThrow("identity constraint lacks persisted authorization");
  expect(await ledger.repairTransitionPlan(committed)).toMatchObject({ idempotent: true, sequence: 1 });

  const reversalAuthorization = { ...authorization, authorization_id: "authorization:alice:reversal", evaluated_frontier: 1 };
  const reversedIdentity = { ...identity, reversed_at: 2, effective_at: 1, identity_authorization: reversalAuthorization };
  const reversal = prepareDerivation({ attempt_id: "attempt:identity:reversal", commit_id: "commit:identity:reversal", owner_account_id: "owner-1", parent_commit: "commit:identity:head", idempotency_key: "identity:reversal", input_revisions: [], output_revisions: [{ revision_id: "a-reversal", content: reversedIdentity }], versions, success_kind: "success" });
  await ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation: reversal, revisions: [{ kind: "identity_authorization", revision_id: "auth:z-reversal", authorization: reversalAuthorization }, { kind: "identity", revision_id: "a-reversal", constraint: reversedIdentity }], adjacency: [], artifacts: [], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirmation:alice", owner_account_id: "owner-1", endpoints: reversalAuthorization.endpoints, relation: "same" }], producer_assertions: [], standing_policies: [] } });
  // `a-reversal` is lexically before the old revision but is the active head by
  // durable sequence; a fresh connection reconstructs the same result.
  expect(ledger.snapshot("owner-1").identity_constraints?.map((item) => item.revision_id)).toEqual(["a-reversal"]);
  const rebuilt = new SqliteLedger(db);
  expect(rebuilt.snapshot("owner-1").identity_constraints?.map((item) => [item.revision_id, item.constraint.reversed_at])).toEqual([["a-reversal", 2]]);
});

test("I8 quarantines unsupported legacy same/distinct constraints and their producing canonical placement idempotently", async () => {
  const db = new Database(":memory:");
  const ledger = new SqliteLedger(db);
  const legacyPlan = transition("legacy:label-only");
  legacyPlan.revisions = legacyPlan.revisions.map((revision) => revision.kind === "claim" && revision.revision_id === "c-1"
    ? { ...revision, claim: { ...revision.claim, evidence_refs: [] } }
    : revision);
  await ledger.appendTransitionPlan(legacyPlan);
  expect(ledger.retrieve({ owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" }).claims.map((item) => item.revision_id)).toEqual(["c-1"]);

  // Synthetic pre-D48 rows: their FK parent exists, but the immutable payloads
  // have only renderings and therefore cannot be made active by that FK alone.
  const labelOnlySame = { constraint_id: "legacy:label:same", owner_account_id: "owner-1", left_handle: "speaker", right_handle: "speaker", relation: "same", effective_at: 1, reversed_at: null };
  const labelOnlyDistinct = { ...labelOnlySame, constraint_id: "legacy:label:distinct", relation: "distinct" as const };
  db.query("UPDATE identity_revisions SET constraint_id = ?, content_json = ? WHERE revision_id = ?").run(labelOnlySame.constraint_id, JSON.stringify(labelOnlySame), "identity:alice:r1");
  db.query("INSERT INTO identity_revisions (revision_id, owner_account_id, content_json, content_hash, commit_id, constraint_id, authorization_revision_id) VALUES (?, ?, ?, ?, ?, ?, ?)").run("legacy:distinct:r1", "owner-1", JSON.stringify(labelOnlyDistinct), "legacy-hash", "commit:legacy:label-only", labelOnlyDistinct.constraint_id, "identity-authorization:alice");

  expect(ledger.quarantineLegacyIdentity()).toEqual({ identity_records: 2, claim_records: 1 });
  expect(ledger.snapshot("owner-1").identity_constraints).toEqual([]);
  expect(ledger.retrieve({ owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" }).claims).toEqual([]);
  expect(ledger.counts()).toMatchObject({ identity_quarantine_records: 2, claim_quarantine_records: 1 });
  expect(ledger.quarantineLegacyIdentity()).toEqual({ identity_records: 0, claim_records: 0 });

  const reloaded = new SqliteLedger(db);
  expect(reloaded.snapshot("owner-1")).toEqual(ledger.snapshot("owner-1"));

  // A later owner confirmation is a new supported transition, not a mutation of
  // quarantined history, and can restore a relation.
  const ownerConfirmed = { ...authorization, authorization_id: "authorization:legacy:reconfirm", evaluated_frontier: 2 };
  const recoveredConstraint = { ...identity, constraint_id: "identity:legacy:recovered", identity_authorization: ownerConfirmed, effective_at: 2 };
  const recovery = prepareDerivation({ attempt_id: "attempt:legacy:recover", commit_id: "commit:legacy:recover", owner_account_id: "owner-1", parent_commit: "commit:legacy:label-only", idempotency_key: "legacy:recover", input_revisions: [], output_revisions: [{ revision_id: "identity:legacy:recovered:r1", content: recoveredConstraint }], versions, success_kind: "success" });
  await reloaded.repairTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation: recovery, revisions: [{ kind: "identity_authorization", revision_id: "identity-authorization:legacy:reconfirm", authorization: ownerConfirmed }, { kind: "identity", revision_id: "identity:legacy:recovered:r1", constraint: recoveredConstraint }], adjacency: [], artifacts: [], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirmation:alice", owner_account_id: "owner-1", endpoints: ownerConfirmed.endpoints, relation: "same" }], producer_assertions: [], standing_policies: [] } });
  expect(reloaded.snapshot("owner-1").identity_constraints?.map((item) => item.constraint.constraint_id)).toEqual(["identity:legacy:recovered"]);
  const afterRepair = reloaded.snapshot("owner-1");
  const converged = new SqliteLedger(db);
  expect(converged.quarantineLegacyIdentity()).toEqual({ identity_records: 0, claim_records: 0 });
  expect(converged.snapshot("owner-1")).toEqual(afterRepair);
});

test("T10 SQLite entity retrieval keeps provisional claims out of entity results", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const unresolved = { ...provisional, claim_revision_id: "p-unresolved", claim_lineage_id: "lineage:unresolved", arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal" as const, value: "He" } }], ambiguity_markers: ["unresolved_subject"] };
  const derivation = prepareDerivation({ attempt_id: "attempt:provisional", commit_id: "commit:provisional", owner_account_id: "owner-1", parent_commit: null, idempotency_key: "key-provisional", input_revisions: [{ revision_id: "p-unresolved", content: unresolved }], output_revisions: [], versions, success_kind: "successful_empty" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [{ input_provisional_revision_id: "p-unresolved", disposition: "defer_review", operation: null, re_resolution_trigger: "new_identity_evidence" }] }, derivation, revisions: [{ kind: "claim", revision_id: "p-unresolved", claim: unresolved, placement_status: "provisional_unresolved_subject" }], adjacency: [], artifacts: [{ artifact_id: "confirmation-queue:p-unresolved", kind: "confirmation_queue", provisional_revision_id: "p-unresolved", canonical_claim_revision_id: null, margin: null, risk_markers: [], unit_boundary_decision: "accept_ltm", scope_locality: null }] });
  const result = ledger.retrieve({ owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" });
  expect(result.claims).toEqual([]);
  expect(result).toEqual({ claims: [], absence: { kind: "query_gap", message: "no cited memory matched" } });
  expect(result).not.toHaveProperty("omission_accounting");
});

test("T9 SQLite round-trips claim evidence through Evidence, Event, Capture, and excerpt", () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  ledger.append(transition());
  const event = { event_id: "event:e1", event_revision_id: "event:e1:r1", owner_account_id: "owner-1", capture_session_id: "capture:roundtrip", stream_id: "stream:roundtrip", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-02", ingest_time: "2026-01-02", source_sequence: 7, evidence_addressable_refs: ["e-1"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "event-hash" };
  const evidence = { evidence_id: "e-1", event_revision_id: "event:e1:r1", source_unit_ref: "unit:1", range: { start: 4, end: 15 }, excerpt: "roundtrip span", source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture:roundtrip" };
  const derivation = prepareDerivation({ attempt_id: "attempt:evidence", commit_id: "commit:evidence", owner_account_id: "owner-1", parent_commit: "commit:key-1", idempotency_key: "key-evidence", input_revisions: [], output_revisions: [{ revision_id: "event:e1:r1", content: event }, { revision_id: "e-1:r1", content: evidence }], versions, success_kind: "success" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions: [{ kind: "event", revision_id: "event:e1:r1", event }, { kind: "evidence", revision_id: "e-1:r1", evidence }], adjacency: [], artifacts: [] });
  const projected = projectTreeInputSnapshot(ledger.snapshot("owner-1"), { account_timezone: "UTC" });
  expect(projected.claims.find((claim) => claim.claim_revision_id === "c-1")?.evidence_spans).toEqual([expect.objectContaining({ evidence_id: "e-1", event_revision_id: "event:e1:r1", capture_session_id: "capture:roundtrip", excerpt: "roundtrip span", range: { start: 4, end: 15 } })]);
  expect(projected.diagnostics).toEqual([]);
});

class DeterministicFakeModel {
  async compose(): Promise<{ answer_text: string; citations: readonly string[] }> { return { answer_text: "not-called", citations: [] }; }
}

test("G2 SQLite adversarial D35: a lexically-smaller tombstone committed later leaves zero owner-visible trace through every read path", async () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const event = { event_id: "event:d35", event_revision_id: "event:d35:r1", owner_account_id: "owner-1", capture_session_id: "capture:d35", stream_id: "stream:d35", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-02T00:00:00Z", ingest_time: "2026-01-02T00:00:00Z", source_sequence: 1, evidence_addressable_refs: ["e-d35"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "event:d35" };
  const active = { evidence_id: "e-d35", event_revision_id: "event:d35:r1", source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: "D35", source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture:d35" };
  const tombstone = { ...active, state: "tombstoned" as const, excerpt: null };
  const citedCanonical = { ...canonical, claim_revision_id: "c-d35", claim_lineage_id: "lineage:d35", canonical_claim_id: "canonical:d35", evidence_refs: ["e-d35"], arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal" as const, value: "D35" } }] };
  const first = prepareDerivation({ attempt_id: "attempt:d35:active", commit_id: "commit:d35:active", owner_account_id: "owner-1", parent_commit: null, idempotency_key: "key:d35:active", input_revisions: [], output_revisions: [{ revision_id: "c-d35", content: citedCanonical }, { revision_id: "event:d35:r1", content: event }, { revision_id: "z-active", content: active }], versions, success_kind: "success" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation: first, revisions: [{ kind: "claim", revision_id: "c-d35", claim: citedCanonical, placement_status: "canonical" }, { kind: "event", revision_id: "event:d35:r1", event }, { kind: "evidence", revision_id: "z-active", evidence: active }], adjacency: [], artifacts: [] });
  expect(ledger.retrieve({ owner_account_id: "owner-1", kind: "as_of", date: "2026-01-03" }).claims.map((item) => item.revision_id)).toEqual(["c-d35"]);

  const second = prepareDerivation({ attempt_id: "attempt:d35:tombstone", commit_id: "commit:d35:tombstone", owner_account_id: "owner-1", parent_commit: "commit:d35:active", idempotency_key: "key:d35:tombstone", input_revisions: [], output_revisions: [{ revision_id: "a-tombstone", content: tombstone }], versions, success_kind: "success" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation: second, revisions: [{ kind: "evidence", revision_id: "a-tombstone", evidence: tombstone }], adjacency: [], artifacts: [] });

  const retracted = ledger.snapshot("owner-1");
  // SQLite presents lexical revision-id order, so an array-order implementation
  // sees the stale `z-active` after the later `a-tombstone`.
  expect(retracted.evidence?.map((item) => [item.revision_id, item.commit_sequence])).toEqual([["a-tombstone", 2], ["z-active", 1]]);
  const neverExisted = { ...retracted, claims: [], adjacency: [] };
  const grant = { grant_id: "owner", policy_classes: [] };
  expect(project(retracted, { reader_account_id: "owner-1", grant })).toEqual(project(neverExisted, { reader_account_id: "owner-1", grant }));
  const input = projectTreeInputSnapshot(retracted, { account_timezone: "UTC" });
  const emptyInput = projectTreeInputSnapshot(neverExisted, { account_timezone: "UTC" });
  expect(input.claims).toEqual([]);
  expect(buildDeterministicAnchors(input)).toEqual(buildDeterministicAnchors(emptyInput));
  expect(ledger.retrieve({ owner_account_id: "owner-1", kind: "as_of", date: "2026-01-03" })).toEqual({ claims: [], absence: { kind: "query_gap", message: "no cited memory matched" } });
  expect(await retrieveDogfood({ owner_account_id: "owner-1", query: "d35", as_of: "2026-01-03", request_context: { reader_account_id: "owner-1", grant } }, retracted, input, [], new DeterministicFakeModel())).toEqual({ answer_text: null, citations: [], hydrated_claim_revision_ids: [], absence: { kind: "query_gap", message: "no cited memory matched" }, grounding: null });
});

test("G2 SQLite adversarial D35: a purge fence survives reconstructing the ledger from the same database", () => {
  const db = new Database(":memory:");
  const ledger = new SqliteLedger(db);
  ledger.append(transition());
  const event = { event_id: "event:purge", event_revision_id: "event:purge:r1", owner_account_id: "owner-1", capture_session_id: "capture:purge", stream_id: "stream:purge", event_kind: "text", payload_schema_ref: "text", schema_version: "v1", payload: {}, event_time: "2026-01-02T00:00:00Z", ingest_time: "2026-01-02T00:00:00Z", source_sequence: 1, evidence_addressable_refs: ["e-1"], source_trust: "test", policy_labels: [], canonical_redacted_hash: "event:purge" };
  const evidence = { evidence_id: "e-1", event_revision_id: "event:purge:r1", source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: "purge fixture", source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "capture:purge" };
  const evidenceCommit = prepareDerivation({ attempt_id: "attempt:purge:evidence", commit_id: "commit:purge:evidence", owner_account_id: "owner-1", parent_commit: "commit:key-1", idempotency_key: "key:purge:evidence", input_revisions: [], output_revisions: [{ revision_id: "event:purge:r1", content: event }, { revision_id: "e-1:active", content: evidence }], versions, success_kind: "success" });
  ledger.append({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation: evidenceCommit, revisions: [{ kind: "event", revision_id: "event:purge:r1", event }, { kind: "evidence", revision_id: "e-1:active", evidence }], adjacency: [], artifacts: [] });
  expect(ledger.retrieve({ owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" }).claims.map((item) => item.revision_id)).toEqual(["c-1"]);
  ledger.purgeClaim("owner-1", "c-1");
  expect(ledger.retrieve({ owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" }).claims).toEqual([]);

  const rebuilt = new SqliteLedger(db);
  expect(rebuilt.snapshot("owner-1").liveness_causes).toEqual({ purged_claim_revision_ids: ["c-1"], forgotten_claim_revision_ids: [] });
  expect(rebuilt.retrieve({ owner_account_id: "owner-1", kind: "entity", entity_id: "entity:alice" })).toEqual({ claims: [], absence: { kind: "query_gap", message: "no cited memory matched" } });
});

test("S2 adversarial restart persists 2020 valid time, never falls back to 2026 observation time, and keeps imprecision honest", () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-s2-reload-"));
  const databaseFile = join(directory, "ledger.sqlite");
  const db = new Database(databaseFile);
  const ledger = new SqliteLedger(db);
  const moved = { ...canonical, claim_revision_id: "c-moved", claim_lineage_id: "lineage:moved", canonical_claim_id: "canonical:moved", evidence_refs: [], temporal_scope: { observed_at: "2026-06-15T12:00:00Z", precision: "instant", valid_time: persistValidTime({ kind: "absolute", granularity: "year", value: "2020" }, { query_at: "2026-06-15T12:00:00Z" }, "UTC") } };
  const plan = transition("temporal", null);
  plan.revisions = plan.revisions.map((revision) => revision.kind === "claim" && revision.revision_id === "c-1" ? { ...revision, revision_id: "c-moved", claim: moved } : revision);
  plan.adjacency = plan.adjacency.map((edge) => edge.claim_revision_id === "c-1" ? { ...edge, claim_revision_id: "c-moved" } : edge);
  plan.artifacts = plan.artifacts.map((artifact) => artifact.canonical_claim_revision_id === "c-1" ? { ...artifact, canonical_claim_revision_id: "c-moved" } : artifact);
  ledger.append(plan);
  db.close();
  // This is a new on-disk connection after the original connection closed.
  const reloadedDb = new Database(databaseFile);
  const reloaded = new SqliteLedger(reloadedDb);
  const input = projectTreeInputSnapshot(reloaded.snapshot("owner-1"), { account_timezone: "UTC" });
  expect(input.claims.find((claim) => claim.claim_revision_id === "c-moved")?.time_anchor).toEqual({ kind: "valid_time", value: "2020-01-01T00:00:00.000Z" });
  const temporalAnchors = buildDeterministicAnchors(input).nodes.filter((node) => node.view_kind === "temporal").map((node) => node.anchor_key);
  expect(temporalAnchors).toContain("year:2020");
  expect(temporalAnchors).not.toContain("year:2026");

  const originalTz = process.env.TZ;
  try {
    process.env.TZ = "UTC";
    const utc = persistValidTime({ kind: "absolute", granularity: "day", value: "2020-06-01" }, { query_at: "2026-01-01T00:00:00Z" }, "UTC");
    process.env.TZ = "America/Los_Angeles";
    const losAngelesAmbient = persistValidTime({ kind: "absolute", granularity: "day", value: "2020-06-01" }, { query_at: "2026-01-01T00:00:00Z" }, "UTC");
    expect(losAngelesAmbient).toEqual(utc);
  } finally { process.env.TZ = originalTz; }

  const imprecise = { ...moved, claim_revision_id: "c-imprecise", claim_lineage_id: "lineage:imprecise", canonical_claim_id: "canonical:imprecise", temporal_scope: { observed_at: "2026-06-15T12:00:00Z", precision: "unknown", valid_time: persistValidTime({ kind: "imprecise", bucket: "unresolved-source-time", precision: "unknown" }, { query_at: "2026-06-15T12:00:00Z" }, "UTC") } };
  const impreciseInput = projectTreeInputSnapshot({ ...reloaded.snapshot("owner-1"), claims: [{ revision_id: "c-imprecise", placement_status: "canonical", claim: imprecise }], adjacency: [] }, { account_timezone: "UTC" });
  expect(impreciseInput.claims[0]!.time_anchor).toEqual({ kind: "imprecise_time", observed_at: "2026-06-15T12:00:00Z", marker: "persisted_imprecise_or_missing_valid_time" });
  expect(buildDeterministicAnchors(impreciseInput).nodes.some((node) => node.anchor_key === "year:2026")).toBe(false);
  const malformedLegacy = { ...imprecise, claim_revision_id: "c-missing", temporal_scope: { observed_at: "2026-06-15T12:00:00Z", precision: "unknown" } };
  const missingInput = projectTreeInputSnapshot({ ...reloaded.snapshot("owner-1"), claims: [{ revision_id: "c-missing", placement_status: "canonical", claim: malformedLegacy as never }], adjacency: [] }, { account_timezone: "UTC" });
  expect(missingInput.claims[0]!.time_anchor.kind).toBe("imprecise_time");
  expect(buildDeterministicAnchors(missingInput).nodes.map((node) => node.anchor_key)).not.toContain("year:2026");
  reloadedDb.close();
  rmSync(directory, { recursive: true, force: true });
});
