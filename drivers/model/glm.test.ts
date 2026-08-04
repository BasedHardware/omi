import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { buildMentionDetectionRequest } from "../../core/resolve/mention-detection";
import { buildScopeRoleRequest } from "../../core/scope/placement";
import type { PersistedValidTime, ProvisionalClaim } from "../../core/schema";
import { SqliteLedger } from "../sqlite";
import { DeterministicFakeModel } from "./port";
import { commitSessionStmToLtmTransition } from "./stm-ltm-transition";
import { buildUnitBoundaryRequest } from "./unit-boundary-edge";
import { EDGES, GlmModel } from "./glm";

const claim = (id = "p-1", surface = "Alice"): ProvisionalClaim => ({
  claim_lineage_id: `lineage:${id}`, claim_revision_id: id, owner_account_id: "owner", predicate: "works_on",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal", value: surface } }],
  temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: [`e:${id}`], policy_labels: [], source_language: "en",
  scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers: [], context_packet: { version: "context-v1", referent_refs: [], topic_refs: [] },
});
const entity = { entity_id: "entity:alice", owner_account_id: "owner", entity_revision_id: "entity:alice:r1", handle: "alice", labels: ["Alice"] };
  const evidenceFor = (item: ProvisionalClaim) => [{ evidence_id: item.evidence_refs[0]!, event_revision_id: `event:${item.claim_revision_id}`, source_unit_ref: item.claim_revision_id, range: { start: 0, end: `${item.arguments[0]!.value.value} works on atlas`.length }, excerpt: `${item.arguments[0]!.value.value} works on atlas`, source_identity_ref: null, speaker_rendering: "speaker:owner", source_local_mention_ref: null, state: "active" as const, source_trust: "fixture", policy_labels: [], source_independence_key: "session" }];

const fixtureProvider = (...contents: string[]) => {
  const calls: unknown[] = [];
  const fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    calls.push(JSON.parse(String(init?.body)));
    const content = contents.shift();
    if (content === undefined) throw new Error("fixture provider ran out of responses");
    return new Response(JSON.stringify({ choices: [{ message: { content } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof globalThis.fetch;
  return { calls, fetch };
};

const modelFor = (provider: ReturnType<typeof fixtureProvider>) => new GlmModel({ apiKey: "fixture-key", baseUrl: "https://fixture.invalid/v1", model: "fixture-glm", fetch: provider.fetch });

test("GLM dispatches entity plus all three placement strategies with deterministic JSON-only chat calls", async () => {
  const provisional = claim();
  const evidence = evidenceFor(provisional);
  const mentionRequest = buildMentionDetectionRequest([provisional], evidence);
  const scopeRequest = buildScopeRoleRequest(provisional, [entity], evidence);
  const boundaryRequest = buildUnitBoundaryRequest(provisional, evidence);
  const provider = fixtureProvider(
    '{"decision":"same","candidate":"c1"}',
    '{"mentions":[{"claim":"k1","slot_id":"subject","surface":"Alice","excerpt":"k1x1","antecedent_handle":null}]}',
    '{"bindings":{"subject":"c1"},"scope_ref":"project:atlas","confidently_placed":true}',
    '{"decision":"accept_ltm","risk_markers":["complete_referents"]}',
  );
  const model = modelFor(provider);

  await expect(model.invoke({ strategy: "local-handle-durable-entity", version: "v1", input: { owner_account_id: "owner", local_handle: { handle: "local:m", mention_ref: "m", antecedent_handle: null, uncertainty: [] }, evidence_refs: ["Alice works on atlas"], candidate_entity_ids: ["entity:alice"], candidate_entities: [{ entity_id: "entity:alice", handle: "alice", labels: ["Alice"] }] } })).resolves.toEqual({ decision: "same", entity_id: "entity:alice" });
  await expect(model.invoke({ strategy: "mention-local-handle", version: "v1", input: mentionRequest })).resolves.toEqual({ mentions: [{ claim_revision_id: "p-1", slot_id: "subject", surface: "Alice", evidence_id: "e:p-1", antecedent_handle: null }] });
  await expect(model.invoke({ strategy: "scope-role-binding", version: "v1", input: scopeRequest })).resolves.toEqual({ bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:atlas" } });
  // The stated risk survives the parse: an edge whose only diagnostic is
  // discarded reports an outcome nobody can review.
  await expect(model.invoke({ strategy: "stm-ltm-unit-boundary", version: "v2", input: boundaryRequest })).resolves.toEqual({ decision: "accept_ltm", risk_markers: ["complete_referents"] });

  expect(provider.calls).toHaveLength(4);
  for (const call of provider.calls as { temperature: number; thinking: { type: string }; response_format: { type: string }; messages: { content: string }[] }[]) {
    expect(call).toMatchObject({ temperature: 0, thinking: { type: "disabled" }, response_format: { type: "json_object" } });
    expect(call.messages[0]!.content).toContain("Return JSON only");
  }
});

test("GLM placement parsers reject malformed model output instead of repairing it", async () => {
  const provisional = claim();
  const evidence = evidenceFor(provisional);
  const mentionRequest = buildMentionDetectionRequest([provisional], evidence);
  const scopeRequest = buildScopeRoleRequest(provisional, [entity], evidence);
  const boundaryRequest = buildUnitBoundaryRequest(provisional, evidence);

  await expect(modelFor(fixtureProvider('{"mentions":[{"claim":"k1","slot_id":"subject","span":{"start":0,"end":5},"excerpt":"k1x1","antecedent_handle":null}]}')).invoke({ strategy: "mention-local-handle", version: "v1", input: mentionRequest })).rejects.toThrow("missing required field: surface");
  await expect(modelFor(fixtureProvider('{"bindings":{"subject":"c9"},"scope_ref":"project:atlas","confidently_placed":true}')).invoke({ strategy: "scope-role-binding", version: "v1", input: scopeRequest })).rejects.toThrow("binds non-candidate entity");
  await expect(modelFor(fixtureProvider('{not json}')).invoke({ strategy: "stm-ltm-unit-boundary", version: "v2", input: boundaryRequest })).rejects.toThrow("was not JSON");
});

test("GLM placement abstentions parse without becoming placement approvals, and unknown strategies still reject", async () => {
  const provisional = claim();
  const evidence = evidenceFor(provisional);
  const mentionRequest = buildMentionDetectionRequest([provisional], evidence);
  const scopeRequest = buildScopeRoleRequest(provisional, [entity], evidence);
  const boundaryRequest = buildUnitBoundaryRequest(provisional, evidence);
  const provider = fixtureProvider(
    '{"mentions":[]}',
    '{"bindings":{"subject":"c1"},"scope_ref":null,"confidently_placed":false}',
    '{"decision":"abstain","risk_markers":["missing_time"]}',
  );
  const model = modelFor(provider);
  await expect(model.invoke({ strategy: "mention-local-handle", version: "v1", input: mentionRequest })).resolves.toEqual({ mentions: [] });
  await expect(model.invoke({ strategy: "scope-role-binding", version: "v1", input: scopeRequest })).resolves.toEqual({ bindings: { subject: "entity:alice" }, scope: null });
  await expect(model.invoke({ strategy: "stm-ltm-unit-boundary", version: "v2", input: boundaryRequest })).resolves.toEqual({ decision: "abstain", reason: "missing_time", risk_markers: ["missing_time"] });
  await expect(model.invoke({ strategy: "not-a-real-edge", version: "v1", input: {} })).rejects.toThrow("does not support strategy");
});

const validTime: PersistedValidTime = { typed_expression: { kind: "absolute", granularity: "year", value: "2026" }, resolved_interval: { kind: "calendar_interval", start: "2026-01-01T00:00:00.000Z", end: "2027-01-01T00:00:00.000Z", timezone: "UTC", granularity: "year" }, derivation: { resolver_version: "fixture", timezone: "UTC" } };

test("all placement fake edges preserve the resolution gate when scope or boundary abstains", async () => {
  const scopeAbstains = claim("p-scope", "Alice");
  const boundaryAbstains = claim("p-boundary", "Alice");
  const provisionals = [scopeAbstains, boundaryAbstains];
  const evidence = provisionals.flatMap(evidenceFor);
  const model = new DeterministicFakeModel((request) => {
    const id = (request.input as { claim_revision_id?: string }).claim_revision_id;
    if (request.strategy === "mention-local-handle") return { mentions: provisionals.map((item) => ({ claim_revision_id: item.claim_revision_id, slot_id: "subject", surface: "Alice", evidence_id: item.evidence_refs[0], antecedent_handle: null })) };
    if (request.strategy === "local-handle-durable-entity") return { decision: "same", entity_id: "entity:alice" };
    if (request.strategy === "scope-role-binding") return id === "p-scope" ? { bindings: { subject: "entity:alice" }, scope: null } : { bindings: { subject: "entity:alice" }, scope: { locality: "durable", scope_ref: "project:atlas" } };
    if (request.strategy === "stm-ltm-unit-boundary") return id === "p-boundary" ? { decision: "abstain", reason: "lost time" } : { decision: "accept_ltm" };
    throw new Error(`unexpected fixture strategy: ${request.strategy}`);
  });
  const ledger = new SqliteLedger(new Database(":memory:"));
  await commitSessionStmToLtmTransition({ ledger, model, session_id: "fixture-gates", owner_account_id: "owner", provisionals, entities: [entity], evidence, valid_times: { "p-scope": validTime, "p-boundary": validTime }, parent_commit: null, versions: { strategy_version: "fixture", model_version: "fixture", prompt_version: "fixture", policy_version: "fixture", code_version: "fixture", schema_version: "fixture", tokenizer_version: "fixture", tool_version: "fixture" } });
  expect(ledger.snapshot("owner").claims.filter((revision) => revision.claim.lifecycle === "canonical")).toHaveLength(0);
});

test("every dispatched prompt shows readable names and asks only for labels back", async () => {
  const profiles = [
    { mention_id: "mention:evidence:9f2a:met:0:subject", claim_revision_id: "provisional:s1:e1:0:met", source_identity_ref: { namespace_instance_ref: "device:7c1e", local_key: "speaker:2", producer: { producer_ref: null, contract_ref: null }, asserted_identity: { domain: null, scope_ref: null } }, discriminating_claims: [{ predicate: "works_on", role: "subject", polarity: "positive" as const, other_arguments: [{ role: "project", value: { kind: "source_local_ref", ref: "source-local:s1:e1:0:5" } }], evidence_context: [{ evidence_ref: "evidence:9f2a", excerpt: "Nora runs the Atlas rollout", capture_session_id: "s1", event_time: null, source_sequence: 1 }], cooccurring_predicates: [], observed_at: "2026-01-01T00:00:00Z", evidence_refs: ["evidence:9f2a"] }] },
    { mention_id: "mention:evidence:3b8d:led:0:subject", claim_revision_id: "provisional:s2:e1:0:led", source_identity_ref: { namespace_instance_ref: "device:7c1e", local_key: "speaker:3", producer: { producer_ref: null, contract_ref: null }, asserted_identity: { domain: null, scope_ref: null } }, discriminating_claims: [{ predicate: "led", role: "subject", polarity: "positive" as const, other_arguments: [], evidence_context: [{ evidence_ref: "evidence:3b8d", excerpt: "She led the Atlas rollout", capture_session_id: "s2", event_time: null, source_sequence: 2 }], cooccurring_predicates: [], observed_at: "2026-01-02T00:00:00Z", evidence_refs: ["evidence:3b8d"] }] },
  ];
  const identityProvider = fixtureProvider('{"same_groups":[["r1","r2"]],"uncertain_pairs":[]}');
  const adjudicated = await modelFor(identityProvider).invoke({ strategy: "identity-adjudication", version: "dream-identity-v1", input: { profiles } });
  const identityPrompt = (identityProvider.calls[0] as { messages: { content: string }[] }).messages[0]!.content;
  for (const id of ["mention:evidence", "provisional:s1", "source-local:", "device:7c1e", "evidence:9f2a"]) expect(identityPrompt).not.toContain(id);
  expect(identityPrompt).toContain("Nora runs the Atlas rollout");
  // Labels are translated back to the real mention ids by the edge, so a model
  // never handles -- or invents -- a durable identifier.
  expect(adjudicated).toEqual({ same_groups: [{ members: [profiles[0]!.mention_id, profiles[1]!.mention_id], who: null, kind: "deictic_or_generic" }], uncertain_pairs: [] });

  const hallucinated = await modelFor(fixtureProvider('{"same_groups":[["r1","r9"]],"uncertain_pairs":[["r1","r9"]]}')).invoke({ strategy: "identity-adjudication", version: "dream-identity-v1", input: { profiles } });
  expect(hallucinated).toEqual({ same_groups: [], uncertain_pairs: [] });
});

test("predicate alignment is asked about names, not about the digests it cannot read", async () => {
  const input = { predicate_frontier: "7", predicates: [
    { predicate_id: "predicate:2a7f9c1e4b6d8a0c3e5f7b9d1a3c5e7f", name: "works_on", slot_ids: ["subject", "project"] },
    { predicate_id: "predicate:8d0f2a4e6c8b1d3f5a7e9c0b2d4f6a8c", name: "is_working_on", slot_ids: ["actor", "project"] },
  ] };
  const provider = fixtureProvider('{"aliases":[{"relation":"p2","means_the_same_as":"p1","slot_aliases":[{"from_slot_id":"actor","to_slot_id":"subject"}]}]}');
  const aligned = await modelFor(provider).invoke({ strategy: "predicate-alignment", version: "dream-predicate-v1", input });
  const prompt = (provider.calls[0] as { messages: { content: string }[] }).messages[0]!.content;
  for (const predicate of input.predicates) expect(prompt).not.toContain(predicate.predicate_id);
  expect(prompt).toContain("is_working_on");
  expect(aligned).toEqual({ assertions: [{ predicate_id: input.predicates[1]!.predicate_id, target_predicate_id: input.predicates[0]!.predicate_id, slot_aliases: [{ from_slot_id: "actor", to_slot_id: "subject" }] }] });
});

test("the entity edge shows the mention it is asked about and refuses a target it was never offered", async () => {
  const request = { owner_account_id: "owner", local_handle: { handle: "local:she", mention_ref: "mention:p-1:subject", antecedent_handle: "local:alice", uncertainty: ["unresolved_local_mention"] }, evidence_refs: ["She works on atlas"], candidate_entity_ids: ["entity:alice"], candidate_entities: [{ entity_id: "entity:alice", handle: "alice", labels: ["Alice"] }] };
  const provider = fixtureProvider('{"decision":"same","candidate":"c1"}');
  await expect(modelFor(provider).invoke({ strategy: "local-handle-durable-entity", version: "v1", input: request })).resolves.toEqual({ decision: "same", entity_id: "entity:alice" });
  const prompt = (provider.calls[0] as { messages: { content: string }[] }).messages[0]!.content;
  expect(prompt).toContain("local:she");
  expect(prompt).toContain("Alice");
  expect(prompt).not.toContain("entity:alice");
  // A candidate id the request never offered cannot become a resolution.
  await expect(modelFor(fixtureProvider('{"decision":"same","candidate":"entity:alice"}')).invoke({ strategy: "local-handle-durable-entity", version: "v1", input: request })).resolves.toEqual({ decision: "abstain" });
});

test("a single malformed claim no longer discards the rest of the extraction batch", async () => {
  const provider = fixtureProvider('{"claims":[{"relation":"met","arguments":[{"slot_id":"a","role":"a","surface":"Alice"}],"polarity":"positive","temporal_expression":{"kind":"imprecise","bucket":"recent","precision":"coarse"},"evidence":"e1"},{"relation":"","arguments":"not-an-array"}]}');
  const parsed = await modelFor(provider).invoke({ strategy: "grounded-extraction", version: "v1", input: { prompt: "x" } }) as { claims: unknown[] };
  // The driver extracts the envelope; the core drops the bad member WITH a
  // recorded reason instead of the whole session throwing on it.
  expect(parsed.claims).toHaveLength(2);
});

const composeInput = { query: "what is Nora working on", evidence_spans: [
  { evidence_id: "evidence:9f2a", excerpt: "Nora runs the Atlas rollout" },
  { evidence_id: "evidence:9f2a", excerpt: "Nora runs the Atlas rollout" },
  { evidence_id: "evidence:3b8d", excerpt: "The rollout ships in March" },
] };

test("the compose edge shows excerpts under short labels and maps the cited labels back to evidence ids", async () => {
  const provider = fixtureProvider('{"answer":"Nora runs the Atlas rollout. It ships in March.","assertions":[{"text":"Nora runs the Atlas rollout.","cites":["s1"]},{"text":"It ships in March.","cites":["s2"]}]}');
  const composed = await modelFor(provider).compose({ strategy: "citation-grounded-compose", version: "v1", input: composeInput });
  const prompt = (provider.calls[0] as { messages: { content: string }[] }).messages[0]!.content;
  for (const id of ["evidence:9f2a", "evidence:3b8d"]) expect(prompt).not.toContain(id);
  expect(prompt).toContain("Nora runs the Atlas rollout");
  expect(prompt).toContain("what is Nora working on");
  // One label per evidence id: a span hydrated twice must not become two citations.
  expect(prompt).toContain('"id": "s2"');
  expect(prompt).not.toContain('"id": "s3"');
  expect(composed).toEqual({
    answer_text: "Nora runs the Atlas rollout. It ships in March.",
    citations: ["evidence:3b8d", "evidence:9f2a"],
    assertions: [{ text: "Nora runs the Atlas rollout.", citations: ["evidence:9f2a"] }, { text: "It ships in March.", citations: ["evidence:3b8d"] }],
  });
});

test("a composed assertion citing a label it was never shown keeps the assertion and loses the citation", async () => {
  const composed = await modelFor(fixtureProvider('{"answer":"Nora runs the Atlas rollout. She also chairs the board.","assertions":[{"text":"Nora runs the Atlas rollout.","cites":["s1","s9"]},{"text":"She also chairs the board.","cites":["s7"]}]}'))
    .compose({ strategy: "citation-grounded-compose", version: "v1", input: composeInput });
  // The unsupported sentence survives the parse with zero citations; the retrieval
  // core reads that as a grounding failure, which is the honest outcome.
  expect(composed.assertions).toEqual([{ text: "Nora runs the Atlas rollout.", citations: ["evidence:9f2a"] }, { text: "She also chairs the board.", citations: [] }]);
  expect(composed.citations).toEqual(["evidence:9f2a"]);
  await expect(modelFor(fixtureProvider('{"answer":"","assertions":[],"note":"nothing here"}')).compose({ strategy: "citation-grounded-compose", version: "v1", input: composeInput })).rejects.toThrow("unexpected field: note");
  await expect(modelFor(fixtureProvider('{"answer":"x"}')).compose({ strategy: "not-a-real-compose", version: "v1", input: composeInput })).rejects.toThrow("compose does not support strategy");
});

test("span entailment defaults to not entailed instead of repairing a verdict it could not read", async () => {
  const input = { assertion: "Nora runs the Atlas rollout.", cited_spans: [{ evidence_id: "evidence:9f2a", excerpt: "Nora runs the Atlas rollout" }] };
  const provider = fixtureProvider('{"entailed":true}');
  await expect(modelFor(provider).invoke({ strategy: "span-entailment", version: "v1", input })).resolves.toEqual({ entailed: true });
  const prompt = (provider.calls[0] as { messages: { content: string }[] }).messages[0]!.content;
  expect(prompt).not.toContain("evidence:9f2a");
  expect(prompt).toContain("Nora runs the Atlas rollout");
  await expect(modelFor(fixtureProvider('{"entailed":"yes"}')).invoke({ strategy: "span-entailment", version: "v1", input })).resolves.toEqual({ entailed: false });
  await expect(modelFor(fixtureProvider('{"entailed":true,"confidence":0.9}')).invoke({ strategy: "span-entailment", version: "v1", input })).rejects.toThrow("unexpected field: confidence");
});

test("the node-summary edge summarizes readable facts and refuses a citation it was never shown", async () => {
  const input = { claims: [{ predicate: "runs", observed_at: "2026-01-02T00:00:00Z", arguments: [{ slot_id: "subject", role: "subject", surface: "Nora", value: { kind: "source_local_ref", ref: "source-local:s1:e1:0:4" } }], evidence_spans: [{ evidence_id: "evidence:9f2a", excerpt: "Nora runs the Atlas rollout" }] }], child_summaries: ["January work"] };
  const provider = fixtureProvider('{"summary":"Nora runs the Atlas rollout.","cites":["s1","s4"]}');
  const rendered = await modelFor(provider).render({ strategy: "retrieval-node-summary", version: "v1", input });
  const prompt = (provider.calls[0] as { messages: { content: string }[] }).messages[0]!.content;
  for (const id of ["evidence:9f2a", "source-local:"]) expect(prompt).not.toContain(id);
  expect(prompt).toContain("Nora runs the Atlas rollout");
  expect(prompt).toContain("January work");
  expect(rendered).toEqual({ summary_text: "Nora runs the Atlas rollout.", citations: ["evidence:9f2a"] });
});

test("the boundary edge is asked about a readable fact, not about our bookkeeping", async () => {
  const provisional: ProvisionalClaim = { ...claim("p-boundary"), arguments: [{ slot_id: "subject", role: "subject", surface: "Alice", value: { kind: "source_local_ref", ref: "source-local:s1:e:p-boundary:0:5" } }], context_packet: { version: "stage-a-context-v1", referent_refs: ["source-local:s1:e:p-boundary:0:5"], topic_refs: ["predicate:4c1e8a0d6b2f9c3e5a7d1b0f2e4c6a8d"] } };
  const provider = fixtureProvider('{"decision":"accept_ltm"}');
  const source = [{ ...evidenceFor(provisional)[0]!, excerpt: "Alice works on atlas", range: { start: 0, end: 20 } }];
  await modelFor(provider).invoke({ strategy: "stm-ltm-unit-boundary", version: "v2", input: buildUnitBoundaryRequest(provisional, source) });
  const prompt = (provider.calls[0] as { messages: { content: string }[] }).messages[0]!.content;
  for (const id of ["source-local:", "predicate:4c1e", "context_packet", "p-boundary"]) expect(prompt).not.toContain(id);
  expect(prompt).toContain("Alice works on atlas");
  expect(prompt).toContain("works_on");
});

test("identity-naming-check parses the contract key, the exact 'answer' alias, and string booleans; any other renamed key fails closed", async () => {
  const provider = fixtureProvider(
    '```json\n{"names_specific_referent": false}\n```',
    '{"answer":"true"}',
    '{"answer":false}',
    '{"is_generic":true}',
  );
  const model = modelFor(provider);
  await expect(model.invoke({ strategy: "identity-naming-check", version: "dream-naming-check-v1", input: { label: "him", surfaces: ["him"] } })).resolves.toEqual({ names_specific_referent: false });
  await expect(model.invoke({ strategy: "identity-naming-check", version: "dream-naming-check-v1", input: { label: "Telegram", surfaces: ["telegram"] } })).resolves.toEqual({ names_specific_referent: true });
  await expect(model.invoke({ strategy: "identity-naming-check", version: "dream-naming-check-v1", input: { label: "700", surfaces: ["700"] } })).resolves.toEqual({ names_specific_referent: false });
  // {"is_generic": true} semantically means REJECT; treating any renamed
  // single key as the verdict would invert it into an admission. It must fail
  // loudly, and the caller's fail-closed catch turns that into a rejection.
  await expect(model.invoke({ strategy: "identity-naming-check", version: "dream-naming-check-v1", input: { label: "x", surfaces: ["x"] } })).rejects.toThrow("identity-naming-check");
  const prompts = (provider.calls as { messages: { content: string }[] }[]).map((call) => call.messages[0]!.content);
  expect(prompts[0]).toContain("UNTRUSTED CONTENT");
});

test("a version the driver does not implement is refused loudly, before any chat call is made", async () => {
  const provider = fixtureProvider('{"verdict":"same","who":"Nora"}');
  const model = modelFor(provider);
  // Version drift used to be invisible: request.version was decorative and any
  // string selected the current prompt. Now the mismatch names both versions.
  await expect(model.invoke({ strategy: "identity-verification", version: "dream-identity-verify-v1", input: { who: "Nora", surfaces: ["Nora"], profiles: [] } }))
    .rejects.toThrow('GLM identity-verification version mismatch: caller requested "dream-identity-verify-v1" but this driver implements "dream-identity-verify-v2"');
  expect(provider.calls).toHaveLength(0);
  await expect(model.invoke({ strategy: "identity-verification", version: "dream-identity-verify-v2", input: { who: "Nora", surfaces: ["Nora"], profiles: [] } })).resolves.toEqual({ verdict: "same", who: "Nora" });
  expect(provider.calls).toHaveLength(1);
});

test("caller-versioned edges accept the version the caller names instead of pinning one", async () => {
  // grounded-extraction's version is a parameter of extractGrounded and is
  // recorded as data; compose/render carry a per-run model_version. None of
  // these name this driver's prompt contract, so no version is pinned.
  await expect(modelFor(fixtureProvider('{"claims":[]}')).invoke({ strategy: "grounded-extraction", version: "stage-a-grounded-v1", input: { prompt: "x" } })).resolves.toEqual({ claims: [] });
  await expect(modelFor(fixtureProvider('{"answer":"","assertions":[]}')).compose({ strategy: "citation-grounded-compose", version: "unspecified", input: composeInput })).resolves.toMatchObject({ answer_text: "" });
  await expect(modelFor(fixtureProvider('{"summary":"","cites":[]}')).render({ strategy: "run-named-render-strategy", version: "glm-4.7", input: {} })).resolves.toEqual({ summary_text: "", citations: [] });
});

test("the edge registry is the single adding-an-edge surface and stays in sync with the strategy union", () => {
  // `EDGES satisfies Record<GlmStrategy, GlmEdge>` enforces the union<->registry
  // sync at compile time; this pins the runtime shape and the invoke surface.
  expect(Object.keys(EDGES).sort()).toEqual([
    "citation-grounded-compose", "grounded-extraction", "identity-adjudication", "identity-naming-check",
    "identity-verification", "local-handle-durable-entity", "mention-local-handle", "predicate-alignment",
    "retrieval-node-summary", "scope-role-binding", "span-entailment", "speaker-self-reference", "stm-ltm-unit-boundary",
  ]);
  for (const edge of Object.values(EDGES)) {
    expect(typeof edge.prompt).toBe("function");
    expect(typeof edge.parse).toBe("function");
    expect(edge.versions === null || edge.versions instanceof Set).toBe(true);
  }
  // The versions pinned here are exactly what core/harness call sites pass today.
  expect(EDGES["identity-verification"].versions).toEqual(new Set(["dream-identity-verify-v2"]));
  expect(EDGES["identity-naming-check"].versions).toEqual(new Set(["dream-naming-check-v1"]));
  expect(EDGES["speaker-self-reference"].versions).toEqual(new Set(["dream-self-reference-v1"]));
  expect(EDGES["identity-adjudication"].versions).toEqual(new Set(["dream-identity-v1"]));
  expect(EDGES["predicate-alignment"].versions).toEqual(new Set(["dream-predicate-v1"]));
});
