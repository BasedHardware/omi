import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import type { PersistedValidTime, ProvisionalClaim } from "../../core/schema";
import { buildFlywheelArtifacts } from "../../core/scope/flywheel";
import { SqliteLedger } from "../sqlite";
import { DeterministicFakeModel } from "./port";
import { commitSessionStmToLtmTransition } from "./stm-ltm-transition";
import { buildUnitBoundaryRequest, invokeUnitBoundaryStrategy } from "./unit-boundary-edge";

const versions = { strategy_version: "s1-v1", model_version: "fake", prompt_version: "p", policy_version: "p", code_version: "c", schema_version: "s", tokenizer_version: "t", tool_version: "t" };
const valid_time: PersistedValidTime = { typed_expression: { kind: "absolute", granularity: "year", value: "2026" }, resolved_interval: { kind: "calendar_interval", start: "2026-01-01T00:00:00.000Z", end: "2027-01-01T00:00:00.000Z", timezone: "UTC", granularity: "year" }, derivation: { resolver_version: "fake-time", timezone: "UTC" } };
const claim = (id: string, surface: string): ProvisionalClaim => ({
  claim_lineage_id: `lineage:${id}`, claim_revision_id: id, owner_account_id: "owner", predicate: "works_on",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal", value: surface } }], observed_speaker_slot_id: "subject", temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: [`e:${id}`], policy_labels: [], source_language: "en", scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers: [], context_packet: { version: "context-v1", referent_refs: [], topic_refs: [] },
});
const provisionals = [claim("p-alice", "Alice"), claim("p-she", "She"), claim("p-it", "it")];
const evidence = provisionals.map((item) => ({ evidence_id: item.evidence_refs[0]!, event_revision_id: `event:${item.claim_revision_id}`, source_unit_ref: item.claim_revision_id, range: { start: 0, end: `${item.arguments[0]!.value.value} works on atlas`.length }, excerpt: `${item.arguments[0]!.value.value} works on atlas`, source_identity_ref: null, speaker_rendering: "speaker:owner", source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "session" }));

test("unit-boundary request drops ambiguous_surface bookkeeping markers", () => {
  const provisional = { ...claim("p-alice", "Alice"), ambiguity_markers: ["ambiguous_surface:subject", "one_off", "hedged"] };
  const request = buildUnitBoundaryRequest(provisional, evidence);
  expect(request.ambiguity_markers).toEqual(["one_off", "hedged"]);
});

test("C2 adversarial session transition commits once, persists returned bindings/scope, excludes abstention, and skips resumed sessions", async () => {
  const sqlite = new SqliteLedger(new Database(":memory:"));
  let commitCalls = 0;
  const ledger = {
    appendTransitionPlan: async (plan: Parameters<SqliteLedger["appendTransitionPlan"]>[0]) => { commitCalls += 1; return sqlite.appendTransitionPlan(plan); },
    findCommitByIdempotencyKey: sqlite.findCommitByIdempotencyKey.bind(sqlite),
  };
  let edgeCalls = 0;
  const model = new DeterministicFakeModel((request) => {
    edgeCalls += 1;
    if (request.strategy === "mention-local-handle") return { mentions: [
      { claim_revision_id: "p-alice", slot_id: "subject", surface: "Alice", evidence_id: "e:p-alice", antecedent_handle: null },
      { claim_revision_id: "p-she", slot_id: "subject", surface: "She", evidence_id: "e:p-she", antecedent_handle: "local:m-alice" },
      { claim_revision_id: "p-it", slot_id: "subject", surface: "it", evidence_id: "e:p-it", antecedent_handle: null },
    ] };
    if (request.strategy === "local-handle-durable-entity") return (request.input as { local_handle: { mention_ref: string } }).local_handle.mention_ref === "mention:p-it:subject" ? { decision: "abstain" } : { decision: "same", entity_id: "entity:alice" };
    if (request.strategy === "stm-ltm-unit-boundary") return (request.input as { claim_revision_id: string }).claim_revision_id === "p-it" ? { decision: "abstain", reason: "insufficient unit" } : { decision: "accept_ltm", margin: "low", risk_markers: ["resolved_pronoun"] };
    if (request.strategy === "scope-role-binding") {
      const id = (request.input as { claim_revision_id: string }).claim_revision_id;
      return id === "p-it" ? { bindings: { subject: null }, scope: null } : { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:model-returned-atlas" } };
    }
    throw new Error(`unexpected strategy ${request.strategy}`);
  });
  const request = { ledger, model, session_id: "session-3", owner_account_id: "owner", provisionals, entities: [{ entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] }], evidence, valid_times: Object.fromEntries(provisionals.map((item) => [item.claim_revision_id, valid_time])), parent_commit: null, versions };
  await commitSessionStmToLtmTransition(request);
  expect(commitCalls).toBe(1);
  const graph = sqlite.snapshot("owner");
  const canonical = graph.claims.filter((item) => item.claim.lifecycle === "canonical");
  expect(canonical).toHaveLength(0);
  expect(canonical.some((item) => item.claim.source_provisional_revision_ids.includes("p-it"))).toBe(false);
  expect(sqlite.mentions("owner")).toContainEqual(expect.objectContaining({ mention_id: "mention:p-it:subject", resolution: "unresolved", entity_id: null, antecedent_handle: null }));
  expect(graph.placement_artifacts?.filter((item) => item.provisional_revision_id === "p-it").map((item) => item.kind)).toEqual(["abstention_set"]);
  expect(graph.placement_artifacts?.some((item) => item.kind === "auto_placement_log")).toBe(false);

  const callsBeforeResume = edgeCalls;
  const resumed = await commitSessionStmToLtmTransition({ ...request, model: new DeterministicFakeModel({ changed: "output must never be read" }) });
  expect(resumed.idempotent).toBe(true);
  expect(commitCalls).toBe(1);
  expect(edgeCalls).toBe(callsBeforeResume);
});

test("C4 unit-boundary sends retained source excerpts and fails closed without one", () => {
  expect(buildUnitBoundaryRequest(provisionals[0]!, evidence)).toMatchObject({ source_excerpts: [{ evidence_id: "e:p-alice", excerpt: "Alice works on atlas" }] });
  expect(() => buildUnitBoundaryRequest(provisionals[0]!, [])).toThrow("lacks retained source excerpt");
});

const singleTransitionRequest = (id: string, surface: string, model: DeterministicFakeModel) => {
  const provisional = claim(id, surface);
  return { ledger: new SqliteLedger(new Database(":memory:")), model, session_id: `session:${id}`, owner_account_id: "owner", provisionals: [provisional], entities: [{ entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] }], evidence: [{ evidence_id: `e:${id}`, event_revision_id: `event:${id}`, source_unit_ref: id, range: { start: 0, end: `${surface} works on atlas`.length }, excerpt: `${surface} works on atlas`, source_identity_ref: null, speaker_rendering: "speaker:owner", source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "session" }], valid_times: { [id]: valid_time }, parent_commit: null, versions };
};

test("D40 adversarial exact sol counterexample: She entity-abstains while scope accepts, so no canonical claim is filed", async () => {
  const request = singleTransitionRequest("p-she-abstains", "She", new DeterministicFakeModel((edge) => {
    if (edge.strategy === "mention-local-handle") return { mentions: [{ claim_revision_id: "p-she-abstains", slot_id: "subject", surface: "She", evidence_id: "e:p-she-abstains", antecedent_handle: null }] };
    if (edge.strategy === "local-handle-durable-entity") return { decision: "abstain" };
    if (edge.strategy === "scope-role-binding") return { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:guessed" } };
    if (edge.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm", margin: "high" };
    throw new Error(`unexpected strategy ${edge.strategy}`);
  }));
  await commitSessionStmToLtmTransition(request);
  const graph = request.ledger.snapshot("owner");
  expect(graph.claims.filter((item) => item.claim.lifecycle === "canonical")).toHaveLength(0);
  expect(graph.claims.find((item) => item.revision_id === "p-she-abstains")?.placement_status).toBe("provisional_abstained");
  expect(request.ledger.mentions("owner")).toContainEqual(expect.objectContaining({ mention_id: "mention:p-she-abstains:subject", slot_id: "subject", resolution: "unresolved", entity_id: null }));
  expect(graph.placement_artifacts?.map((artifact) => artifact.kind)).toEqual(["confirmation_queue"]);
});

test("D40 adversarial empty mention response forces unresolved She and cannot auto-place it", async () => {
  const request = singleTransitionRequest("p-empty-mentions", "She", new DeterministicFakeModel((edge) => {
    if (edge.strategy === "mention-local-handle") return { mentions: [] };
    if (edge.strategy === "local-handle-durable-entity") throw new Error("a forced unresolved mention must not be guessed through entity resolution");
    if (edge.strategy === "scope-role-binding") return { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:guessed" } };
    if (edge.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm", margin: "high" };
    throw new Error(`unexpected strategy ${edge.strategy}`);
  }));
  await commitSessionStmToLtmTransition(request);
  expect(request.ledger.snapshot("owner").claims.filter((item) => item.claim.lifecycle === "canonical")).toHaveLength(0);
  expect(request.ledger.mentions("owner")).toContainEqual(expect.objectContaining({ claim_revision_id: "p-empty-mentions", slot_id: "subject", resolution: "unresolved", entity_id: null }));
});

test("D47 adversarial: a fake model's naked same cannot auto-place a fully resolved role", async () => {
  const request = singleTransitionRequest("p-alice-resolved", "Alice", new DeterministicFakeModel((edge) => {
    if (edge.strategy === "mention-local-handle") return { mentions: [{ claim_revision_id: "p-alice-resolved", slot_id: "subject", surface: "Alice", evidence_id: "e:p-alice-resolved", antecedent_handle: null }] };
    if (edge.strategy === "local-handle-durable-entity") return { decision: "same", entity_id: "entity:alice" };
    if (edge.strategy === "scope-role-binding") return { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:real" } };
    if (edge.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm", margin: "high" };
    throw new Error(`unexpected strategy ${edge.strategy}`);
  }));
  await commitSessionStmToLtmTransition(request);
  const canonical = request.ledger.snapshot("owner").claims.filter((item) => item.claim.lifecycle === "canonical");
  expect(canonical).toHaveLength(0);
});

test("D40 adversarial same-plus-abstain rows for one slot persist the abstention and gate canonical placement", async () => {
  const request = singleTransitionRequest("p-same-abstain", "Alice", new DeterministicFakeModel((edge) => {
    if (edge.strategy === "mention-local-handle") return { mentions: [
      { claim_revision_id: "p-same-abstain", slot_id: "subject", surface: "Alice", evidence_id: "e:p-same-abstain", antecedent_handle: null },
      { claim_revision_id: "p-same-abstain", slot_id: "subject", surface: "Alice", evidence_id: "e:p-same-abstain", antecedent_handle: null },
    ] };
    if (edge.strategy === "local-handle-durable-entity") return (edge.input as { local_handle: { mention_ref: string } }).local_handle.mention_ref === "mention:p-same-abstain:subject"
      ? { decision: "same", entity_id: "entity:alice" }
      : { decision: "abstain" };
    if (edge.strategy === "scope-role-binding") return { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:guessed" } };
    if (edge.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm", margin: "high" };
    throw new Error(`unexpected strategy ${edge.strategy}`);
  }));
  await commitSessionStmToLtmTransition(request);
  const graph = request.ledger.snapshot("owner");
  expect(graph.claims.filter((item) => item.claim.lifecycle === "canonical")).toHaveLength(0);
  expect(request.ledger.mentions("owner")).toEqual(expect.arrayContaining([
    expect.objectContaining({ mention_id: "mention:p-same-abstain:subject", resolution: "unresolved", entity_id: null }),
    expect.objectContaining({ mention_id: "mention:p-same-abstain:subject:1", resolution: "unresolved", entity_id: null }),
  ]));
});

test("D40 adversarial duplicate party slot IDs are rejected before a model can collapse Alice and Bob onto one role", async () => {
  const malformed: ProvisionalClaim = {
    ...claim("p-duplicate-party", "Alice"),
    arguments: [
      { slot_id: "party", role: "subject", value: { kind: "literal", value: "Alice" } },
      { slot_id: "party", role: "object", value: { kind: "literal", value: "Bob" } },
    ],
  };
  let modelCalls = 0;
  const request = {
    ...singleTransitionRequest("p-duplicate-party", "Alice", new DeterministicFakeModel(() => {
      modelCalls += 1;
      throw new Error("malformed claims must be rejected before model invocation");
    })),
    provisionals: [malformed],
  };
  await expect(commitSessionStmToLtmTransition(request)).rejects.toThrow("distinct slot_ids");
  expect(modelCalls).toBe(0);
  expect(request.ledger.snapshot("owner").claims.filter((item) => item.claim.lifecycle === "canonical")).toHaveLength(0);
});

test("D47 adversarial: targetless model distinct cannot mint or later merge a durable entity", async () => {
  const minted = claim("p-minted", "Nora");
  const sameNora = claim("p-same-nora", "Nora");
  const existing = claim("p-existing", "Alice");
  const mintedEntityId = "entity:owner:session:minted-census:m-nora";
  const request = {
    ledger: new SqliteLedger(new Database(":memory:")), session_id: "session:minted-census", owner_account_id: "owner", provisionals: [minted, sameNora, existing],
    entities: [{ entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] }],
    evidence: [minted, sameNora, existing].map((item) => ({ evidence_id: item.evidence_refs[0]!, event_revision_id: `event:${item.claim_revision_id}`, source_unit_ref: item.claim_revision_id, range: { start: 0, end: `${item.arguments[0]!.value.value} works on atlas`.length }, excerpt: `${item.arguments[0]!.value.value} works on atlas`, source_identity_ref: null, speaker_rendering: "speaker:owner", source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "session" })),
    valid_times: { "p-minted": valid_time, "p-same-nora": valid_time, "p-existing": valid_time }, parent_commit: null, versions,
    model: new DeterministicFakeModel((edge) => {
      if (edge.strategy === "mention-local-handle") return { mentions: [
        { claim_revision_id: "p-minted", slot_id: "subject", surface: "Nora", evidence_id: "e:p-minted", antecedent_handle: null },
        { claim_revision_id: "p-same-nora", slot_id: "subject", surface: "Nora", evidence_id: "e:p-same-nora", antecedent_handle: null },
        { claim_revision_id: "p-existing", slot_id: "subject", surface: "Alice", evidence_id: "e:p-existing", antecedent_handle: null },
      ] };
      if (edge.strategy === "local-handle-durable-entity") return (edge.input as { local_handle: { mention_ref: string } }).local_handle.mention_ref === "mention:p-minted:subject"
        ? { decision: "distinct" }
        : (edge.input as { local_handle: { mention_ref: string } }).local_handle.mention_ref === "mention:p-same-nora:subject"
          ? { decision: "same", entity_id: mintedEntityId }
          : { decision: "same", entity_id: "entity:alice" };
      if (edge.strategy === "scope-role-binding") return (edge.input as { claim_revision_id: string }).claim_revision_id === "p-minted"
        ? { bindings: { subject: mintedEntityId }, scope: { locality: "durable", scope_ref: "project:nora" } }
        : (edge.input as { claim_revision_id: string }).claim_revision_id === "p-same-nora"
          ? { bindings: { subject: mintedEntityId }, scope: { locality: "durable", scope_ref: "project:nora" } }
        : { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:alice" } };
      if (edge.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm", margin: "high" };
      throw new Error(`unexpected strategy ${edge.strategy}`);
    }),
  };
  await commitSessionStmToLtmTransition(request);
  const graph = request.ledger.snapshot("owner");
  expect(graph.entities.map((item) => item.entity.entity_id)).not.toContain(mintedEntityId);
  const mintedArtifact = graph.placement_artifacts?.find((item) => item.provisional_revision_id === "p-minted");
  const sameNoraArtifact = graph.placement_artifacts?.find((item) => item.provisional_revision_id === "p-same-nora");
  const existingArtifact = graph.placement_artifacts?.find((item) => item.provisional_revision_id === "p-existing");
  expect(mintedArtifact?.kind).toBe("confirmation_queue");
  expect(sameNoraArtifact?.kind).toBe("confirmation_queue");
  expect(existingArtifact?.kind).toBe("confirmation_queue");
});

test("D41 adversarial model low-risk claim cannot suppress graph-derived new-entity or resolved-pronoun provenance", async () => {
  const provisional = claim("p-new-risk", "She");
  const source = [{ evidence_id: "e:p-new-risk", event_revision_id: "event:p-new-risk", source_unit_ref: "p-new-risk", range: { start: 0, end: 18 }, excerpt: "She works on atlas", source_identity_ref: null, speaker_rendering: "speaker:owner", source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "session" }];
  const boundary = await invokeUnitBoundaryStrategy(new DeterministicFakeModel({ decision: "accept_ltm", margin: "high", risk_markers: [] }), provisional, source);
  expect(boundary).not.toHaveProperty("risk_markers");
  const artifacts = buildFlywheelArtifacts({
    provisional_revision_id: provisional.claim_revision_id, canonical_claim_revision_id: "canonical:new-risk",
    scope_plan: { bindings: { subject: "entity:new" }, scope: { locality: "durable", scope_ref: "project:new" }, abstained_slots: [], scope_abstained: false, confidently_placed: true },
    unit_boundary: boundary,
    mentions: [{ mention_id: "m-new-risk", owner_account_id: "owner", claim_revision_id: provisional.claim_revision_id, span: { start: 0, end: 3 }, evidence_id: "e:p-new-risk", speaker_ref: "speaker:owner", slot_id: "subject", surface: "She", antecedent_handle: null, resolution: "resolved", entity_id: "entity:new" }],
    newly_minted_entity_ids: ["entity:new"],
  });
  expect(artifacts[0]!.risk_markers).toEqual(expect.arrayContaining(["new_entity", "resolved_pronoun"]));
});

test("P0-a adversarial: a non-zero caller frontier admits exactly its owner-confirmed binding", async () => {
  const identity = { namespace_instance_ref: "namespace:frontier", local_key: "alice", producer: { producer_ref: null, contract_ref: null }, asserted_identity: { domain: null, scope_ref: null } };
  const authorization = { authorization_id: "auth:frontier:9", owner_account_id: "owner", endpoints: [{ kind: "source_identity" as const, source_identity_ref: identity }, { kind: "entity" as const, entity_id: "entity:alice" }], relation: "same" as const, support: { kind: "owner_confirmation" as const, confirmation_ref: "confirm:frontier:9" }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: identity.namespace_instance_ref, identity_domain: null, scope_ref: null }, authority_policy_version: "identity-policy:v1", evaluated_frontier: 9, actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active" as const, superseded_by: null };
  const model = new DeterministicFakeModel((edge) => {
    if (edge.strategy === "mention-local-handle") return { mentions: [{ claim_revision_id: "p-frontier", slot_id: "subject", surface: "Alice", evidence_id: "e:p-frontier", antecedent_handle: null }] };
    if (edge.strategy === "local-handle-durable-entity") return { decision: "same", entity_id: "entity:alice" };
    if (edge.strategy === "scope-role-binding") return { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "entity:alice" } };
    if (edge.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm", margin: "high" };
    throw new Error(`unexpected strategy ${edge.strategy}`);
  });
  const base = singleTransitionRequest("p-frontier", "Alice", model);
  const request = { ...base, graph_frontier: 9, evidence: [{ ...base.evidence[0]!, source_identity_ref: identity }], identity_authorizations: [authorization], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirm:frontier:9", owner_account_id: "owner", endpoints: authorization.endpoints, relation: "same" as const }], producer_assertions: [], standing_policies: [] } };
  await commitSessionStmToLtmTransition(request);
  expect(request.ledger.snapshot("owner").claims.filter((item) => item.claim.lifecycle === "canonical").map((item) => item.revision_id)).toEqual(["canonical:owner:session:p-frontier:p-frontier"]);

  const wrong = { ...request, ledger: new SqliteLedger(new Database(":memory:")), session_id: "session:frontier-wrong", identity_authorizations: [{ ...authorization, authorization_id: "auth:frontier:8", evaluated_frontier: 8 }], identity_authority_context: { owner_confirmations: [{ confirmation_ref: "confirm:frontier:9", owner_account_id: "owner", endpoints: authorization.endpoints, relation: "same" as const }], producer_assertions: [], standing_policies: [] } };
  await commitSessionStmToLtmTransition(wrong);
  expect(wrong.ledger.snapshot("owner").claims.filter((item) => item.claim.lifecycle === "canonical")).toHaveLength(0);
});

test("I5 adversarial mixed batch canonicalizes only fully identity-authorized claims", async () => {
  const good = claim("p-good", "Alice");
  const bad = claim("p-bad", "Bob");
  const pair: ProvisionalClaim = { ...claim("p-pair", "Alice"), arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal", value: "Alice" } }, { slot_id: "object", role: "object", value: { kind: "literal", value: "Bob" } }] };
  const identities = ["good", "bad", "pair-a", "pair-b"].map((key) => ({ namespace_instance_ref: `namespace:${key}`, local_key: key, producer: { producer_ref: null, contract_ref: null }, asserted_identity: { domain: null, scope_ref: null } }));
  const authorize = (identity: typeof identities[number], entity_id: string) => ({ authorization_id: `auth:${identity.local_key}`, owner_account_id: "owner", endpoints: [{ kind: "source_identity" as const, source_identity_ref: identity }, { kind: "entity" as const, entity_id }], relation: "same" as const, support: { kind: "owner_confirmation" as const, confirmation_ref: `confirm:${identity.local_key}` }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: identity.namespace_instance_ref, identity_domain: null, scope_ref: null }, authority_policy_version: "identity-policy:v1", evaluated_frontier: 12, actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active" as const, superseded_by: null });
  const authorizations = [authorize(identities[0]!, "entity:alice"), authorize(identities[2]!, "entity:alice")];
  const evidence = [good, bad, pair].flatMap((item) => item.arguments.map((argument, index) => ({ evidence_id: index === 0 ? `e:${item.claim_revision_id}` : `e:${item.claim_revision_id}:${argument.slot_id}`, event_revision_id: `event:${item.claim_revision_id}`, source_unit_ref: `unit:${item.claim_revision_id}`, range: { start: 0, end: 18 }, excerpt: "Alice met Bob today", source_identity_ref: item.claim_revision_id === "p-good" ? identities[0]! : item.claim_revision_id === "p-bad" ? identities[1]! : index === 0 ? identities[2]! : identities[3]!, speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "session" })));
  // Each claim deliberately cites its first source; the two-role claim's object
  // is still a separate typed mention, so its missing authorization blocks all.
  pair.evidence_refs = ["e:p-pair", "e:p-pair:object"];
  const model = new DeterministicFakeModel((edge) => {
    if (edge.strategy === "mention-local-handle") return { mentions: [
      { claim_revision_id: "p-good", slot_id: "subject", surface: "Alice", evidence_id: "e:p-good", antecedent_handle: null },
      { claim_revision_id: "p-bad", slot_id: "subject", surface: "Bob", evidence_id: "e:p-bad", antecedent_handle: null },
      { claim_revision_id: "p-pair", slot_id: "subject", surface: "Alice", evidence_id: "e:p-pair", antecedent_handle: null },
      { claim_revision_id: "p-pair", slot_id: "object", surface: "Bob", evidence_id: "e:p-pair:object", antecedent_handle: null },
    ] };
    if (edge.strategy === "local-handle-durable-entity") return { decision: "same", entity_id: (edge.input as { local_handle: { mention_ref: string } }).local_handle.mention_ref.endsWith("b") ? "entity:bob" : "entity:alice" };
    if (edge.strategy === "scope-role-binding") return { bindings: Object.fromEntries((edge.input as { entity_role_slots: string[] }).entity_role_slots.map((slot) => [slot, slot === "object" ? "entity:bob" : "entity:alice"])), scope: { locality: "durable", scope_ref: "batch" } };
    if (edge.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm", margin: "high" };
    throw new Error(`unexpected strategy ${edge.strategy}`);
  });
  const ledger = new SqliteLedger(new Database(":memory:"));
  await commitSessionStmToLtmTransition({ ledger, model, session_id: "mixed", owner_account_id: "owner", graph_frontier: 12, provisionals: [good, bad, pair], entities: [{ entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "alice:r1", handle: "alice", labels: [] }, { entity_id: "entity:bob", owner_account_id: "owner", entity_revision_id: "bob:r1", handle: "bob", labels: [] }], evidence, valid_times: { "p-good": valid_time, "p-bad": valid_time, "p-pair": valid_time }, parent_commit: null, versions, identity_authorizations: authorizations, identity_authority_context: { owner_confirmations: authorizations.map((authorization) => ({ confirmation_ref: (authorization.support as { confirmation_ref: string }).confirmation_ref, owner_account_id: "owner", endpoints: authorization.endpoints, relation: "same" as const })), producer_assertions: [], standing_policies: [] } });
  expect(ledger.snapshot("owner").claims.filter((item) => item.claim.lifecycle === "canonical").map((item) => item.claim.source_provisional_revision_ids[0])).toEqual(["p-good"]);
});
