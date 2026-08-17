import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { prepareDerivation, type AtomicGraphTransition } from "../core/ledger";
import { SqliteLedger } from "../drivers/sqlite";
import { answerQuestion, recallLogPath, type RecallModelPort } from "./recall";

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
const recallModel = (compose: RecallModelPort["compose"]): RecallModelPort => {
  let step = 0;
  return {
    agentStep: async (messages) => {
      step += 1;
      const question = (() => {
        try {
          const firstUser = messages.find((message) => message.role === "user");
          return firstUser ? String((JSON.parse(firstUser.content) as { question?: string }).question ?? "Atlas") : "Atlas";
        } catch {
          return "Atlas";
        }
      })();
      if (step === 1) return { tool: "search", args: { query: question, limit: 8 } };
      // After search, pick evidence ids from the tool result in the last user message.
      const last = [...messages].reverse().find((message) => message.role === "user" && message.content.includes("hits"));
      const hits = last ? (JSON.parse(last.content) as { hits?: { evidence_ids?: string[] }[] }).hits ?? [] : [];
      const evidence_ids = hits.flatMap((hit) => hit.evidence_ids ?? []).slice(0, 4);
      return { tool: "done", args: { evidence_ids } };
    },
    compose,
    invoke: async () => ({ entailed: true }),
  };
};
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

test("owner recall that never calls done still answers from accumulated search hits", async () => {
  const db = await ledgerWithMemories();
  let composeCalls = 0;
  const neverDone: RecallModelPort = {
    agentStep: async () => ({ tool: "search", args: { query: "Atlas", limit: 8 } }),
    compose: async ({ input }) => {
      composeCalls += 1;
      return composeFromMatchingSpan({ input });
    },
    invoke: async () => ({ entailed: true }),
  };
  const answer = await answerQuestion({ db, owner_account_id: owner, query: "Atlas", model: neverDone });
  expect(answer).toMatchObject({ answer_text: "Nora runs the Atlas rollout.", citations: ["evidence:atlas"], absence: null, grounding: { status: "grounded" } });
  expect(answer.agent_trace?.every((step) => step.tool === "search")).toBe(true);
  expect(composeCalls).toBe(1);
});

test("owner recall salvages entailed assertions when answer prose overreaches", async () => {
  const db = await ledgerWithMemories();
  let composeCalls = 0;
  const smuggled = async ({ input }: { input: unknown }) => {
    composeCalls += 1;
    const span = (input as ComposeCall).evidence_spans[0]!;
    return { answer_text: `${span.excerpt}. The rollout finished ahead of schedule.`, citations: [span.evidence_id], assertions: [{ text: `${span.excerpt}.`, citations: [span.evidence_id] }] };
  };
  const answer = await answerQuestion({ db, owner_account_id: owner, query: "Atlas", model: recallModel(smuggled) });
  // Manifest mismatch triggers repair; salvage keeps the entailed assertion only.
  expect(composeCalls).toBe(2);
  expect(answer).toMatchObject({ absence: null, grounding: { status: "grounded" } });
  expect(answer.answer_text).toContain("Nora runs the Atlas rollout");
  expect(answer.answer_text).not.toContain("ahead of schedule");
  expect(answer.citations).toEqual(["evidence:atlas"]);
});

test("owner recall query_gaps when no assertion entails", async () => {
  const db = await ledgerWithMemories();
  const model: RecallModelPort = {
    agentStep: async () => ({ tool: "search", args: { query: "Atlas", limit: 8 } }),
    compose: async ({ input }) => {
      const span = (input as ComposeCall).evidence_spans[0]!;
      return { answer_text: "Invented fact.", citations: [span.evidence_id], assertions: [{ text: "Invented fact.", citations: [span.evidence_id] }] };
    },
    invoke: async () => ({ entailed: false }),
  };
  const answer = await answerQuestion({ db, owner_account_id: owner, query: "Atlas", model });
  expect(answer).toMatchObject({ answer_text: null, citations: [], absence: { kind: "query_gap", message: "no cited memory matched" }, grounding: null });
  expect(answer.cited_spans).toEqual([]);
});

test("owner recall appends a versioned JSONL log for every answerQuestion call", async () => {
  const db = await ledgerWithMemories();
  const log_dir = mkdtempSync(join(tmpdir(), "recall-log-"));
  try {
    expect(recallLogPath(db, "agentic-recall-v2", log_dir)).toBe(join(log_dir, "agentic-recall-v2.jsonl"));
    await answerQuestion({ db, owner_account_id: owner, query: "Atlas", model: recallModel(composeFromMatchingSpan), log_dir, model_version: "agentic-recall-v2" });
    await answerQuestion({ db, owner_account_id: owner, query: "kayaking", model: recallModel(composeFromMatchingSpan), log_dir, model_version: "agentic-recall-v2" });
    const lines = readFileSync(join(log_dir, "agentic-recall-v2.jsonl"), "utf8").trim().split("\n").map((line) => JSON.parse(line));
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({
      schema_version: "recall_log.v3",
      model_version: "agentic-recall-v2",
      query: "Atlas",
      answer_text: "Nora runs the Atlas rollout.",
      grounded_assertion_citations: [{ ordinal: 0, citations: ["evidence:atlas"] }],
      grounding: "grounded",
      absence: null,
    });
    expect(lines[0].cited_spans).toBeUndefined();
    expect(lines[0].agent_trace).toBeUndefined();
    expect(Array.isArray(lines[0].tools)).toBe(true);
    expect(lines[1]).toMatchObject({ query: "kayaking", absence: "query_gap", answer_text: null });
    expect(typeof lines[0].ms).toBe("number");
    expect(typeof lines[0].recorded_at).toBe("string");
    expect(typeof lines[0].host).toBe("string");
  } finally {
    rmSync(log_dir, { recursive: true, force: true });
  }
});
