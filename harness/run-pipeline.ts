import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import { Database } from "bun:sqlite";
import { extractGrounded, materializeGroundedMentions, materializeGroundedProvisional } from "../core/extract/grounded";
import { checkRelationDistribution, type QualityFinding } from "../core/extract/quality";
import { ingestConversation } from "../core/extract/ingest";
import { prepareDerivation, type AtomicGraphTransition } from "../core/ledger";
import { getWritingContext } from "../core/retrieve/writing-context";
import { assertNoLookahead, type StmItem } from "../core/stm/replay";
import { proposeProfileOverlaps } from "../core/consolidate/identity";
import { shouldConsolidate } from "../core/consolidate/trigger";
import { SqliteLedger } from "../drivers/sqlite";
import { runSqliteDreamCycle, SqliteDreamStore } from "../drivers/sqlite/dream";
import { SqliteStmStore, type DurableStmItem } from "../drivers/sqlite/stm";
import { writeGraphBrowserExport } from "./graph-export";
import { selectDreamModel, selectModel, type ModelSelection } from "./model-select";

type Adapter = { producer_ref: string; contract_ref: string; namespace_instance_ref: string; asserted_identity_domain: string | null; scope_ref: string | null; issuer_ref: string; authority_policy_version: string };
type Segment = { event_id: string; text: string; start_at: string; speaker_label: string | null; speaker_id: string; is_actor_user?: boolean | null; person_id?: string | null; revision_lineage: string; ingest_sequence: number; settled_window_id: string };
type Session = { session_id: string; capture_sequence: number; revision_lineage: string; ingest_sequence: number; settled_window_id: string; adapter?: Adapter; source_trust?: string; event_kind?: string; segments: readonly Segment[] };
type Corpus = { owner_account_id: string; adapter: Adapter; source_trust?: string; event_kind?: string; sessions: readonly Session[] };

const digest = (value: unknown): string => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const terms = (text: string): readonly string[] => [...new Set(text.toLocaleLowerCase().match(/[\p{L}\p{N}_-]+/gu) ?? [])];
const versions = { strategy_version: "stage-a-grounded-v1", model_version: "none", prompt_version: "none", policy_version: "stage-a-v1", code_version: "stage-a-v1", schema_version: "stage-a-v1", tokenizer_version: "none", tool_version: "stage-a-v1" };

const readCorpus = (path: string): Corpus => {
  const corpus: unknown = JSON.parse(readFileSync(path, "utf8"));
  const schema = JSON.parse(readFileSync(new URL("./corpus.schema.json", import.meta.url), "utf8"));
  const validate = new Ajv2020({ allErrors: true }).compile(schema);
  if (!validate(corpus)) throw new Error(`invalid corpus: ${validate.errors?.map((error) => `${error.instancePath || "/"} ${error.message}`).join("; ")}`);
  return corpus as Corpus;
};

// Identity coordinates: owner attestation wins over person_id (matches
// coldrun_adapter / D-b subject:owner). A bare diarization channel is
// session-scoped — "speaker:2" tomorrow is a different throat.
const sourceIdentity = (adapter: Adapter, session_id: string, segment: Segment) => ({ namespace_instance_ref: adapter.namespace_instance_ref, local_key: segment.is_actor_user ? "person:owner" : segment.person_id ? `person:${segment.person_id}` : `speaker:${session_id}:${segment.speaker_id}`, producer: { producer_ref: adapter.producer_ref, contract_ref: adapter.contract_ref }, asserted_identity: { domain: adapter.asserted_identity_domain, scope_ref: adapter.scope_ref } });

const ingest = async (ledger: SqliteLedger, corpus: Corpus, session: Session, parent_commit: string | null) => {
  const adapter = session.adapter ?? corpus.adapter;
  const source_trust = session.source_trust ?? corpus.source_trust;
  const event_kind = session.event_kind ?? corpus.event_kind;
  const ingested = ingestConversation({ owner_account_id: corpus.owner_account_id, capture_session_id: session.session_id, stream_id: "stage-a", source_trust, event_kind, payload_schema_ref: event_kind, utterances: session.segments.map((segment) => ({ source_unit_ref: segment.event_id, speaker_rendering: segment.speaker_label ?? (segment.is_actor_user ? "owner" : `speaker ${segment.speaker_id}`), source_identity_ref: sourceIdentity(adapter, session.session_id, segment), mention_ref: segment.speaker_id, text: segment.text, event_time: segment.start_at })) });
  const events = ingested.events.map((event, index) => ({ ...event, event_id: session.segments[index]!.event_id, source_sequence: session.segments[index]!.ingest_sequence, payload: { ...event.payload, is_actor_user: session.segments[index]!.is_actor_user ?? null, person_id: session.segments[index]!.person_id ?? null, adapter } }));
  const revisions: AtomicGraphTransition["revisions"] = [
    ...events.map((event) => ({ kind: "event" as const, revision_id: event.event_revision_id, event })),
    ...ingested.evidence.map((evidence) => ({ kind: "evidence" as const, revision_id: `evidence-revision:${evidence.evidence_id}`, evidence })),
  ];
  const derivation = prepareDerivation({ attempt_id: `stage-a-ingest-attempt:${session.session_id}`, commit_id: `stage-a-ingest:${session.session_id}`, owner_account_id: corpus.owner_account_id, parent_commit, idempotency_key: `stage-a-ingest:${corpus.owner_account_id}:${session.session_id}`, input_revisions: [], output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: revision.kind === "event" ? revision.event : revision.evidence })), versions, success_kind: "success" });
  await ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions, adjacency: [], artifacts: [] });
  return ingested.evidence;
};

const syntheticClaims = (evidence: readonly ReturnType<typeof ingestConversation>["evidence"][number][]) => evidence.flatMap((item, index) => {
  const label = `e${index + 1}`, dense = [...item.excerpt!.matchAll(/(Referent\d+)\s+(predicate\d+)/g)];
  if (dense.length) return dense.map((match) => ({ relation: `utterance.${match[2]!.toLocaleLowerCase()}`, arguments: [{ slot_id: "subject", role: "subject", surface: match[1]! }], polarity: "positive" as const, temporal_expression: { kind: "absolute" as const, granularity: "instant" as const, value: item.event_revision_id }, evidence: label, observed_speaker_slot_id: null }));
  const speaker = item.excerpt!.match(/[\p{L}\p{N}_-]+/u)?.[0] ?? "speaker";
  const arguments_ = [{ slot_id: "speaker", role: "speaker", surface: speaker }];
  if (item.excerpt!.includes("Alice")) arguments_.push({ slot_id: "person", role: "person", surface: "Alice" });
  return { relation: `utterance.${speaker.toLocaleLowerCase()}`, arguments: arguments_, polarity: /\bnot\b/i.test(item.excerpt!) ? "negative" as const : "positive" as const, temporal_expression: { kind: "absolute" as const, granularity: "instant" as const, value: item.event_revision_id }, evidence: label, observed_speaker_slot_id: "speaker" };
});

/** Deterministic subject class: owner fills a claim role via self-reference on person:owner evidence. */
export const subjectPolicyLabels = (
  claim: { observed_speaker_slot_id?: string | null; arguments: readonly { slot_id: string }[]; evidence_refs: readonly string[] },
  evidence: readonly { evidence_id: string; source_identity_ref?: { local_key: string } | null }[],
): readonly string[] => {
  const speakerSlot = claim.observed_speaker_slot_id;
  if (!speakerSlot || !claim.arguments.some((argument) => argument.slot_id === speakerSlot)) return ["subject:generic"];
  const byId = new Map(evidence.map((item) => [item.evidence_id, item]));
  for (const ref of claim.evidence_refs) {
    const key = byId.get(ref)?.source_identity_ref?.local_key;
    if (key === "person:owner") return ["subject:owner"];
    if (key) return ["subject:bystander"];
  }
  return ["subject:generic"];
};

const itemFor = (session: Session, claim: ReturnType<typeof materializeGroundedProvisional>, evidence: readonly ReturnType<typeof ingestConversation>["evidence"][number][], argument_origins: Readonly<Record<string, "suggested" | "independent">>): DurableStmItem => {
  const labeled = { ...claim, policy_labels: [...subjectPolicyLabels(claim, evidence)] };
  return {
    id: labeled.claim_revision_id, session_id: session.session_id, event_time_watermark: labeled.temporal_scope.observed_at,
    capture_sequence: session.capture_sequence, revision_lineage: session.revision_lineage, ingest_sequence: session.ingest_sequence,
    entity_refs: [...new Set(labeled.arguments.flatMap((argument) => argument.value.kind === "source_local_ref" ? [argument.value.ref] : []))],
    lexical_terms: terms(`${labeled.predicate} ${labeled.arguments.map((argument) => argument.surface ?? "").join(" ")}`), vector_key: digest(labeled.predicate),
    predicate_id: labeled.predicate, bytes: JSON.stringify(labeled).length, claim: labeled, evidence, argument_origins, settled_window_id: session.settled_window_id,
  };
};

/**
 * Production does not discard a person's memories because one call failed, so
 * neither does this. Transient provider errors (rate limits, 5xx, timeouts) are
 * retried with backoff; a deterministic rejection -- a malformed response, a
 * prompt the provider refuses -- is not retried, because repeating it produces
 * the same answer and only costs money.
 */
const transient = (error: unknown): boolean => {
  const message = error instanceof Error ? error.message : String(error);
  return /\b(429|500|502|503|504)\b/.test(message) || /timeout|ECONNRESET|fetch failed|socket/i.test(message);
};
const withRetry = async <T>(label: string, run: () => Promise<T>, attempts = 3): Promise<T> => {
  for (let attempt = 1; ; attempt += 1) {
    try { return await run(); } catch (error) {
      if (attempt >= attempts || !transient(error)) throw error;
      const backoffMs = 500 * 2 ** (attempt - 1);
      console.error(`retry ${attempt}/${attempts - 1} for ${label} in ${backoffMs}ms: ${error instanceof Error ? error.message : error}`);
      await new Promise((resolve) => setTimeout(resolve, backoffMs));
    }
  }
};

export interface RunPipelineResult { digest: string; model_calls: number; sessions: number; stm_items: number; sessions_resumed: number; dream_cycles: number; dream_failures: readonly { cycle: number; reason: string }[]; quality_findings: readonly QualityFinding[]; }
export interface RunPipelineDependencies {
  selectModel?: (input: { session_id: string; hermetic_seed: unknown }) => ModelSelection;
  selectDreamModel?: (hermetic: Parameters<typeof selectDreamModel>[1]) => ModelSelection;
}

const option = (options: readonly string[], name: string): string | undefined => {
  const index = options.indexOf(name);
  return index < 0 ? undefined : options[index + 1];
};

export const runPipeline = async (argv: readonly string[], dependencies: RunPipelineDependencies = {}): Promise<RunPipelineResult> => {
  const [corpusPath, ...options] = argv;
  if (!corpusPath) throw new Error("usage: bun run harness/run-pipeline.ts <corpus-path> --db path [--export path] [--max-sessions n] [--batch n] [--model glm]");
  const dbPath = option(options, "--db");
  if (!dbPath) throw new Error("--db is required");
  const maxOption = option(options, "--max-sessions"), maxSessions = maxOption === undefined ? Infinity : Number(maxOption), batchSize = Number(option(options, "--batch") ?? 1);
  if (maxOption !== undefined && (!Number.isInteger(maxSessions) || maxSessions < 1)) throw new Error("--max-sessions must be a positive integer");
  if (!Number.isInteger(batchSize) || batchSize < 1) throw new Error("--batch must be a positive integer");

  const corpus = readCorpus(corpusPath), db = new Database(dbPath), ledger = new SqliteLedger(db), stm = new SqliteStmStore(db);
  const sessions = [...corpus.sessions].sort((left, right) => left.segments[0]!.start_at.localeCompare(right.segments[0]!.start_at) || left.capture_sequence - right.capture_sequence || left.revision_lineage.localeCompare(right.revision_lineage) || left.ingest_sequence - right.ingest_sequence || left.session_id.localeCompare(right.session_id)).slice(0, maxSessions);
  let parent = ledger.graphHead(corpus.owner_account_id)?.commit_id ?? null;
  const dreamFailures: { cycle: number; reason: string }[] = [];
  let calls = 0, dreamCycles = 0, lastTriggerTokens = 0;
  // Resume must not reuse prior cycle_ids: dream-mentions/predicate idempotency
  // keys include the cycle id, and a collided key with new mention content throws
  // after promotion already committed (stranding the rest of the cycle).
  let cycleCounter = new SqliteDreamStore(db).trajectories(corpus.owner_account_id).length;
  let previousWindow: string | null = null, previousEventTime: string | null = null;
  const relations: string[] = [];

  // Resume falls out of the ledger, not a parallel bookkeeping table. "Done"
  // requires BOTH the ingest commit and extracted STM items: ingest commits
  // before extraction, so a session killed between the two would otherwise be
  // skipped forever with no claims. Re-running such a session is safe -- the
  // ingest replay no-ops on its idempotency key. (A session that honestly
  // extracted zero claims is re-extracted on every resume; rare and cheap.)
  const extractedSessions = new Set(stm.all().map((item) => item.session_id));
  const alreadyDone = (session: Session): boolean =>
    ledger.findCommitByIdempotencyKey(`stage-a-ingest:${corpus.owner_account_id}:${session.session_id}`) !== null
    && extractedSessions.has(session.session_id);
  const pending = sessions.filter((session) => !alreadyDone(session));
  const resumed = sessions.length - pending.length;
  if (resumed) console.error(`resuming: ${resumed} session(s) already committed, ${pending.length} to go`);
  // A BACKFILL is a pending session whose ingest commit already exists: it was
  // reached in correct event-time order by a previous run and lost only its
  // extraction (crash between ingest and stm.put, or a zero-claim pass). The
  // lookahead assert below rightly forbids extracting a session behind the STM
  // frontier during forward progress; for a backfill the invariant is already
  // discharged by the prior run's ordered ingest, and extraction itself is a
  // pure function of the session, so re-extracting cannot leak the future.
  const backfillSessions = new Set(pending.filter((session) => ledger.findCommitByIdempotencyKey(`stage-a-ingest:${corpus.owner_account_id}:${session.session_id}`) !== null).map((session) => session.session_id));
  if (backfillSessions.size) console.error(`backfilling extraction for ${backfillSessions.size} previously ingested session(s)`);

  const dreamOnce = async (triggerKind: "volume" | "idle" | "end_of_stream", windowLabel: string): Promise<void> => {
    cycleCounter += 1;
    const hermetic = {
      async invoke(request: { strategy: string; input: unknown }) {
        if (request.strategy === "predicate-alignment") return { assertions: [] };
        if (request.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm" };
        if (request.strategy === "scope-role-binding") return { bindings: {}, scope: { locality: "durable", scope_ref: "hermetic:durable" } };
        if (request.strategy === "identity-verification") return { verdict: "same", who: (request.input as { surfaces?: readonly string[] }).surfaces?.[0] ?? null };
        if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
        if (request.strategy === "speaker-self-reference") return { self_referring: ((request.input as { phrases?: readonly string[] }).phrases ?? []).map(() => true) };
        const profiles = (request.input as { profiles?: Parameters<typeof proposeProfileOverlaps>[0] }).profiles ?? [];
        return { same_groups: proposeProfileOverlaps(profiles).slice(0, 1), uncertain_pairs: [] };
      },
      async render() { return { summary_text: "", citations: [] }; },
      async compose() { return { answer_text: "", citations: [], assertions: [] }; },
    };
    const selection = dependencies.selectDreamModel?.(hermetic) ?? selectDreamModel(options, hermetic);
    // Provenance must name the model that actually adjudicated this cycle:
    // live GLM runs stamp the live model id, hermetic runs stamp the fake.
    const modelVersion = selection.live ? (process.env.OMI_BENCH_OPENAI_MODEL ?? "glm-4.7") : "deterministic-fake-v1";
    // A consolidation failure costs you consolidation, not the extraction run.
    // Dream is the experimental half; committed memories must not be discarded
    // because one merge could not satisfy the ledger.
    let deferredIds: readonly string[] = [];
    try {
      const report = await runSqliteDreamCycle({ db, ledger, owner_account_id: corpus.owner_account_id, stm_items: stm.unconsumed(), stm_mentions: stm.mentions(), model: selection.model, cycle_id: `cycle:${cycleCounter}:${windowLabel}`, trigger_kind: triggerKind, model_version: modelVersion });
      deferredIds = report.deferred;
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      dreamFailures.push({ cycle: cycleCounter, reason });
      console.error(`dream cycle ${cycleCounter} failed: ${reason}`);
    }
    dreamCycles += 1;
    // DRAIN: ledger consumed markers cover admits + deferred commits; report.deferred
    // also covers crash-recovery skips that already had an idempotency commit.
    const deferred = new Set(deferredIds);
    stm.consume(stm.unconsumed().filter((item) => ledger.isProvisionalConsumed(item.claim.claim_revision_id) || deferred.has(item.id)).map((item) => item.id));
    lastTriggerTokens = stm.unconsumed().reduce((sum, item) => sum + item.bytes, 0);
    parent = ledger.graphHead(corpus.owner_account_id)?.commit_id ?? parent;
  };

  for (let offset = 0; offset < pending.length; offset += batchSize) {
    const batch = pending.slice(offset, offset + batchSize);
    const ingested: { session: Session; evidence: readonly ReturnType<typeof ingestConversation>["evidence"][number][] }[] = [];
    for (const session of batch) {
      const evidence = await ingest(ledger, corpus, session, parent);
      parent = ledger.graphHead(corpus.owner_account_id)?.commit_id ?? parent;
      ingested.push({ session, evidence });
    }

    const graph = ledger.snapshot(corpus.owner_account_id), frontier = stm.unconsumed();
    const extracted = await Promise.all(ingested.map(async ({ session, evidence }) => {
      const current: StmItem = { id: `session:${session.session_id}`, session_id: session.session_id, event_time_watermark: session.segments[0]!.start_at, capture_sequence: session.capture_sequence, revision_lineage: session.revision_lineage, ingest_sequence: session.ingest_sequence, entity_refs: [], lexical_terms: [], vector_key: "session", predicate_id: "session", bytes: 0 };
      if (!backfillSessions.has(session.session_id)) assertNoLookahead(current, frontier);
      const context = getWritingContext(graph, { account_timezone: "UTC", policy_version: versions.policy_version, predicate_alias_generation: "none", authorization_generation: "none", stm_generation: frontier.map((item) => item.id).join(":") || "empty", window: { text: session.segments.map((segment) => segment.text).join(" ") } });
      const seed = { claims: syntheticClaims(evidence) };
      const model = dependencies.selectModel?.({ session_id: session.session_id, hermetic_seed: seed }).model ?? selectModel(options, seed).model;
      calls += 1;
      try {
        const extraction = await withRetry(session.session_id, () => extractGrounded(model, { context, predicate_registry: context.predicate_signatures.map((signature) => signature.name), entity_registry: context.entity_candidates.map((candidate) => candidate.ref), evidence, version: "stage-a-grounded-v1" }));
        const outputs = extraction.claims.map((emission, claim_index) => {
          const claim = materializeGroundedProvisional({ owner_account_id: corpus.owner_account_id, session_id: session.session_id, observed_at: session.segments[0]!.start_at, source_language: "unknown", context, claim_index, emission });
          return { item: itemFor(session, claim, evidence, emission.argument_origins), mentions: materializeGroundedMentions({ owner_account_id: corpus.owner_account_id, claim, claim_index, mentions: extraction.mentions }) };
        });
        return { session, extraction, outputs };
      } catch (error) {
        console.error(`extraction failed for ${session.session_id}: ${error instanceof Error ? error.message : error}`);
        return null;
      }
    }));

    for (const entry of extracted) if (entry) {
      stm.put(entry.outputs);
      relations.push(...entry.extraction.claims.map((claim) => claim.predicate_ref));
      for (const drop of entry.extraction.dropped) console.error(`drop ${entry.session.session_id}: ${drop.reason}${drop.relation ? ` (${drop.relation})` : ""}`);
      for (const finding of entry.extraction.quality_findings) console.error(`quality ${entry.session.session_id}: ${finding.code}: ${finding.detail}`);
    }

    const last = batch[batch.length - 1]!, settledEventTime = last.segments[last.segments.length - 1]!.start_at;
    const trigger = shouldConsolidate({ stm_tokens: stm.unconsumed().reduce((sum, item) => sum + item.bytes, 0), last_trigger_stm_tokens: lastTriggerTokens, high_watermark_tokens: 1_000_000, low_watermark_tokens: 500_000, previous_settled_window_id: previousWindow, previous_settled_event_time: previousEventTime, settled_window_id: last.settled_window_id, settled_event_time: settledEventTime, idle_gap_ms: 6 * 60 * 60 * 1000 });
    if (trigger.fire) await dreamOnce(trigger.kind, last.settled_window_id);
    previousWindow = last.settled_window_id;
    previousEventTime = settledEventTime;
  }

  // END-OF-STREAM FLUSH: the tail of a corpus arrives after the last trigger,
  // so without this final cycle every export under-reports whatever the last
  // sessions said. Runs on the unconsumed frontier only; the cycle id is a
  // pure function of how many cycles preceded it, so replays agree.
  if (stm.unconsumed().length) await dreamOnce("end_of_stream", "end-of-stream");

  const quality_findings = checkRelationDistribution(relations);
  for (const finding of quality_findings) console.error(`quality run: ${finding.code}: ${finding.detail}`);
  const exportPath = option(options, "--export");
  if (exportPath) writeGraphBrowserExport(exportPath, ledger.snapshot(corpus.owner_account_id), new SqliteDreamStore(db).trajectories(corpus.owner_account_id));
  return { digest: digest(corpus), model_calls: calls, sessions: sessions.length, sessions_resumed: resumed, stm_items: stm.all().length, dream_cycles: dreamCycles, dream_failures: dreamFailures, quality_findings };
};

if (import.meta.main) runPipeline(Bun.argv.slice(2)).then((result) => console.log(JSON.stringify(result))).catch((error) => { console.error(error instanceof Error ? error.message : error); process.exitCode = 1; });
