import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { prepareDerivation, type AtomicGraphTransition } from "../core/ledger";
import { SqliteLedger } from "../drivers/sqlite";
import { answerQuestion, type RecallModelPort } from "./recall";

const owner = "recall-test-owner";
const versions = { strategy_version: "test", model_version: "deterministic-fake-v1", prompt_version: "test", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "none", tool_version: "test" };
const validTime = (day: string) => ({ typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: `${day}T09:00:00Z` }, resolved_interval: { kind: "instant" as const, start: `${day}T09:00:00Z`, end: `${day}T09:00:00Z`, timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } });

const seedClaim = (id: string, predicate: string, excerpt: string, day: string) => {
  const identity = { namespace_instance_ref: `namespace:${id}`, local_key: id, producer: { producer_ref: "test", contract_ref: "test" }, asserted_identity: { domain: null, scope_ref: null } };
  const event = { event_id: `event:${id}`, event_revision_id: `event:${id}`, owner_account_id: owner, capture_session_id: `session:${id}`, stream_id: "test", event_kind: "text", payload_schema_ref: "test", schema_version: "v1", payload: {}, event_time: `${day}T09:00:00Z`, ingest_time: `${day}T09:00:00Z`, source_sequence: 0, evidence_addressable_refs: [`evidence:${id}`], source_trust: "test", policy_labels: [], canonical_redacted_hash: `event:${id}` };
  const evidence = { evidence_id: `evidence:${id}`, event_revision_id: event.event_revision_id, source_unit_ref: id, range: { start: 0, end: excerpt.length }, excerpt, source_identity_ref: identity, speaker_rendering: null, source_local_mention_ref: id, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: `capture:${id}` };
  const provisional = { claim_lineage_id: `lineage:${id}`, claim_revision_id: `provisional:${id}`, owner_account_id: owner, predicate, arguments: [{ slot_id: "subject", role: "subject", surface: excerpt.split(" ")[0]!, value: { kind: "source_local_ref" as const, ref: `source-local:${id}` } }], temporal_scope: { observed_at: `${day}T09:00:00Z`, precision: "instant" as const }, evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: { version: "v1", referent_refs: [], topic_refs: [] } };
  const { ambiguity_markers: _ambiguity, context_packet: _context, ...canonicalBase } = provisional;
  const canonical = { ...canonicalBase, claim_revision_id: `canonical:${id}`, temporal_scope: { ...provisional.temporal_scope, valid_time: validTime(day) }, lifecycle: "canonical" as const, canonical_claim_id: `canonical:${id}`, source_provisional_revision_ids: [provisional.claim_revision_id] };
  return { event, evidence, provisional, canonical };
};

const seed = async (ledger: SqliteLedger, claims: readonly ReturnType<typeof seedClaim>[]) => {
  const revisions: AtomicGraphTransition["revisions"] = claims.flatMap((item) => [
    { kind: "event" as const, revision_id: item.event.event_revision_id, event: item.event },
    { kind: "evidence" as const, revision_id: `evidence-revision:${item.evidence.evidence_id}`, evidence: item.evidence },
    { kind: "claim" as const, revision_id: item.provisional.claim_revision_id, claim: item.provisional, placement_status: "consumed" as const },
    { kind: "claim" as const, revision_id: item.canonical.claim_revision_id, claim: item.canonical, placement_status: "canonical" as const },
  ]);
  const derivation = prepareDerivation({ attempt_id: "seed-attempt", commit_id: "seed", owner_account_id: owner, parent_commit: null, idempotency_key: "seed", input_revisions: [], output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: revision.kind === "event" ? revision.event : revision.kind === "evidence" ? revision.evidence : revision.claim })), versions, success_kind: "success" });
  await ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: Object.fromEntries(claims.map((item) => [item.provisional.claim_revision_id, item.canonical.claim_revision_id])), results: claims.map((item) => ({ input_provisional_revision_id: item.provisional.claim_revision_id, disposition: "admit" as const, operation: null })) }, derivation, revisions, adjacency: [], artifacts: claims.map((item) => ({ artifact_id: `auto-placement:${item.provisional.claim_revision_id}`, kind: "auto_placement_log" as const, provisional_revision_id: item.provisional.claim_revision_id, canonical_claim_revision_id: item.canonical.claim_revision_id, margin: null, risk_markers: [], unit_boundary_decision: "accept_ltm" as const, scope_locality: "durable" as const })) });
};

const ledgerWithMemories = async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  await seed(ledger, [
    seedClaim("atlas", "runs", "Nora runs the Atlas rollout", "2026-01-02"),
    seedClaim("tap", "fixed", "Sam fixed the kitchen tap", "2026-01-02"),
    seedClaim("lisbon", "booked", "I booked a flight to Lisbon", "2026-01-03"),
  ]);
  return db;
};

type ComposeCall = { query: string; evidence_spans: readonly { evidence_id: string; excerpt: string }[] };
/** A summary is what a question is matched against, so the fake writes the same readable
 * text a real render edge would: the node's relations plus its excerpts. */
const recallModel = (compose: RecallModelPort["compose"]): RecallModelPort => ({
  render: async ({ input }) => {
    const claims = (input as { claims: readonly { predicate: string; evidence_spans: readonly { excerpt: string | null }[] }[] }).claims;
    return { summary_text: claims.map((claim) => `${claim.predicate} ${claim.evidence_spans.map((span) => span.excerpt ?? "").join(" ")}`).join(" | "), citations: [] };
  },
  compose,
  invoke: async () => ({ entailed: true }),
});
const composeFromMatchingSpan = async ({ input }: { input: unknown }) => {
  const { query, evidence_spans } = input as ComposeCall;
  const span = evidence_spans.find((candidate) => candidate.excerpt.toLocaleLowerCase().includes(query.toLocaleLowerCase())) ?? evidence_spans[0]!;
  return { answer_text: `${span.excerpt}.`, citations: [span.evidence_id], assertions: [{ text: `${span.excerpt}.`, citations: [span.evidence_id] }] };
};

test("owner recall answers from a live ledger and returns the excerpt and capture behind every citation", async () => {
  const db = await ledgerWithMemories();
  const answer = await answerQuestion({ db, owner_account_id: owner, query: "Atlas", model: recallModel(composeFromMatchingSpan) });
  expect(answer).toMatchObject({ answer_text: "Nora runs the Atlas rollout.", citations: ["evidence:atlas"], absence: null, grounding: { status: "grounded" } });
  expect(answer.hydrated_claim_revision_ids).toContain("canonical:atlas");
  expect(answer.cited_spans).toEqual([{ evidence_id: "evidence:atlas", excerpt: "Nora runs the Atlas rollout", capture_session_id: "session:atlas" }]);
});

test("owner recall discloses a query gap rather than composing an answer nothing supports", async () => {
  const db = await ledgerWithMemories();
  const answer = await answerQuestion({ db, owner_account_id: owner, query: "kayaking", model: recallModel(composeFromMatchingSpan) });
  expect(answer).toMatchObject({ answer_text: null, citations: [], absence: { kind: "query_gap", message: "no cited memory matched" }, grounding: null });
  expect(answer.cited_spans).toEqual([]);
});

test("owner recall refuses an answer whose extra sentence is absent from the grounding manifest", async () => {
  const db = await ledgerWithMemories();
  const smuggled = async ({ input }: { input: unknown }) => {
    const span = (input as ComposeCall).evidence_spans[0]!;
    return { answer_text: `${span.excerpt}. The rollout finished ahead of schedule.`, citations: [span.evidence_id], assertions: [{ text: `${span.excerpt}.`, citations: [span.evidence_id] }] };
  };
  const answer = await answerQuestion({ db, owner_account_id: owner, query: "Atlas", model: recallModel(smuggled) });
  expect(answer).toMatchObject({ answer_text: null, citations: [], absence: null, grounding: { status: "ungrounded" } });
  expect(answer.grounding?.status === "ungrounded" && answer.grounding.failures).toContain("answer assertion is absent from grounding manifest: The rollout finished ahead of schedule.");
  expect(answer.cited_spans).toEqual([]);
});
