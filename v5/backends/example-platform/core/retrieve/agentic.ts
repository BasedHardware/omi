import { compareStrings } from "../order";
import { project, walk, type GraphSnapshot, type LiveClaimView, type TreeInputSnapshot } from "./index";
import type { RequestContext } from "./grant";
import type { AbsenceDisclosure, ComposeModelPort, DogfoodResponse } from "./dogfood";

/** Host-side tools the walk agent may call. Topology stays out of the model. */
export type AgenticToolName = "search" | "walk" | "inspect" | "list_surfaces" | "done";
export interface AgenticToolCall {
  tool: AgenticToolName;
  args: Record<string, unknown>;
}
export interface AgenticChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}
export interface AgenticModelPort extends ComposeModelPort {
  /** One agent turn. Caller keeps messages stable-prefix for prompt cache. */
  agentStep(messages: readonly AgenticChatMessage[]): Promise<AgenticToolCall>;
}

export interface AgenticRequest {
  owner_account_id: string;
  query: string;
  as_of?: string;
  request_context: RequestContext;
  /** ponytail: hard caps; raise if walks starve on denser graphs. */
  max_steps?: number;
  max_evidence?: number;
}

const words = (text: string) => text.toLocaleLowerCase().split(/[^\p{L}\p{N}_-]+/u).filter((w) => w.length > 1);
const STOP = new Set(["who", "what", "when", "where", "which", "the", "and", "are", "is", "in", "of", "to", "my", "me", "do", "does", "a", "an", "for", "with", "about", "you", "your", "be", "on", "at", "it", "this", "that", "from"]);
/** Pronouns skipped by list_surfaces — not useful argument surfaces. */
const PRONOUN_SURFACE = /^(i|me|you|we|us|it|they|them)$/iu;

const argSurface = (argument: LiveClaimView["arguments"][number]): string => {
  const surface = (argument as { surface?: string }).surface;
  if (surface) return surface;
  const value = argument.value;
  if (value.kind === "literal") return String(value.value);
  if (value.kind === "entity_ref" || value.kind === "source_local_ref") return value.ref;
  return "";
};

const claimText = (claim: LiveClaimView): string => {
  const args = claim.arguments.map(argSurface);
  const excerpts = claim.evidence_spans.map((span) => span.excerpt ?? "").join(" ");
  return [claim.predicate, ...args, ...claim.policy_labels, excerpts].join(" ");
};

/** Keep first occurrence of each evidence_id (compose budget is per-id, not per-claim). */
const uniqByEvidenceId = <T extends { evidence_id: string }>(spans: readonly T[]): T[] => {
  const seen = new Set<string>();
  return spans.filter((span) => {
    if (seen.has(span.evidence_id)) return false;
    seen.add(span.evidence_id);
    return true;
  });
};

/** Dumb lexical overlap — no query-class expansion or domain boosts. */
const scoreClaim = (query: string, claim: LiveClaimView): number => {
  const q = words(query).filter((w) => !STOP.has(w));
  const hay = new Set(words(claimText(claim)));
  let score = 0;
  for (const w of q) if (hay.has(w)) score += 1;
  return score;
};

const summarizeClaim = (claim: LiveClaimView) => ({
  claim_revision_id: claim.claim_revision_id,
  status: claim.placement_status,
  predicate: claim.predicate,
  labels: claim.policy_labels,
  args: claim.arguments.map((argument) => (argument as { surface?: string }).surface ?? (argument.value.kind === "literal" ? String(argument.value.value) : argument.value.kind === "entity_ref" || argument.value.kind === "source_local_ref" ? argument.value.ref : "")),
  evidence_ids: claim.evidence_spans.map((span) => span.evidence_id),
  excerpt: claim.evidence_spans.map((span) => span.excerpt).filter(Boolean).slice(0, 1)[0]?.slice(0, 220) ?? null,
});

/** Stable system prompt — keep byte-identical across turns for prompt cache. */
export const AGENTIC_SYSTEM_PROMPT = `You are a memory-graph retrieval agent for ONE owner. You may only use the tools below. Return JSON only: {"tool":"<name>","args":{...}}.

Tools:
- search: {"query":"string","limit":number} — lexical search over live durable claims (canonical + unresolved). Reformulate the query yourself across calls; the host does not expand it. Deferred/abstained dream rejects are not searchable.
- walk: {"anchor":"claim:<id>|entity:<id>|capture:<uuid>","max_hops":1|2,"limit":number} — BFS over typed adjacency on the safe projection.
- inspect: {"claim_revision_id":"string"} — full claim + evidence excerpts.
- list_surfaces: {"limit":number} — frequent argument surfaces (with owner flag); you judge what matters.
- done: {"evidence_ids":["evidence:..."],"note":"string"} — finish with evidence ids from tool results (or [] if nothing relevant). Never invent ids.

Strategy:
1. Explore within the step budget: search, reformulate, inspect, walk as needed, then call done when ready.
2. Prefer inspect before inventing. Call done with real evidence_ids from tool results only.`;

const parseToolCall = (raw: AgenticToolCall): AgenticToolCall => {
  if (!raw || typeof raw !== "object") throw new Error("agentic tool call must be an object");
  const tool = raw.tool;
  if (tool !== "search" && tool !== "walk" && tool !== "inspect" && tool !== "list_surfaces" && tool !== "done") throw new Error(`unknown agentic tool: ${String(tool)}`);
  return { tool, args: raw.args && typeof raw.args === "object" ? raw.args as Record<string, unknown> : {} };
};

export const runAgenticTools = (input: TreeInputSnapshot, graph: GraphSnapshot, request: AgenticRequest, call: AgenticToolCall): { result: unknown; done?: { evidence_ids: string[] } } => {
  const byId = new Map(input.claims.map((claim) => [claim.claim_revision_id, claim]));
  const safe = project(graph, request.request_context);
  const searchable = input.claims.filter((claim) => claim.placement_status !== "provisional_abstained");

  if (call.tool === "search") {
    const query = String(call.args.query ?? request.query);
    const limit = Math.min(Number(call.args.limit) || 12, 30);
    // Dream abstention is bookkeeping: those claims were judged non-durable. Searching them
    // reintroduces sludge into recall (bitter-lesson: don't undo the curator with a soft read path).
    const ranked = searchable
      .map((claim) => ({ claim, score: scoreClaim(query, claim) }))
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score || compareStrings(a.claim.claim_revision_id, b.claim.claim_revision_id))
      .slice(0, limit)
      .map((row) => ({ score: row.score, ...summarizeClaim(row.claim) }));
    return { result: { hits: ranked } };
  }

  if (call.tool === "list_surfaces") {
    const limit = Math.min(Number(call.args.limit) || 40, 80);
    const counts = new Map<string, { count: number; owner: boolean; claim_ids: string[] }>();
    for (const claim of searchable) {
      const ownerLabeled = claim.policy_labels.includes("subject:owner");
      for (const argument of claim.arguments) {
        const surface = argSurface(argument).trim();
        if (!surface || surface.length > 40 || PRONOUN_SURFACE.test(surface)) continue;
        const row = counts.get(surface) ?? { count: 0, owner: false, claim_ids: [] };
        row.count += 1;
        row.owner = row.owner || ownerLabeled;
        if (row.claim_ids.length < 3) row.claim_ids.push(claim.claim_revision_id);
        counts.set(surface, row);
      }
    }
    const surfaces = [...counts.entries()]
      .map(([name, row]) => ({ name, ...row }))
      .sort((a, b) => b.count - a.count || Number(b.owner) - Number(a.owner) || compareStrings(a.name, b.name))
      .slice(0, limit);
    return { result: { surfaces } };
  }

  if (call.tool === "inspect") {
    const id = String(call.args.claim_revision_id ?? "");
    const claim = byId.get(id);
    if (!claim) return { result: { error: "unknown claim_revision_id" } };
    return {
      result: {
        ...summarizeClaim(claim),
        excerpts: claim.evidence_spans.map((span) => ({ evidence_id: span.evidence_id, excerpt: span.excerpt, capture_session_id: span.capture_session_id })),
      },
    };
  }

  if (call.tool === "walk") {
    const anchor = String(call.args.anchor ?? "");
    const max_hops = Math.min(Math.max(Number(call.args.max_hops) || 1, 0), 2);
    const limit = Math.min(Number(call.args.limit) || 20, 40);
    try {
      const walked = walk(safe, { anchor, max_hops, result_cap: limit });
      const claimIds = [...new Set(walked.paths.flatMap((path) => path.nodes).filter((node) => node.startsWith("claim:")).map((node) => node.slice("claim:".length)))];
      return {
        result: {
          node_count: walked.node_count,
          edge_count: walked.edge_count,
          claims: claimIds.slice(0, limit).map((id) => byId.get(id)).filter(Boolean).map((claim) => summarizeClaim(claim!)),
          sample_paths: walked.paths.slice(0, 8).map((path) => ({ nodes: path.nodes, hops: path.hops.map((hop) => hop.relation_kind) })),
        },
      };
    } catch (error) {
      return { result: { error: error instanceof Error ? error.message : String(error) } };
    }
  }

  const evidence_ids = Array.isArray(call.args.evidence_ids)
    ? call.args.evidence_ids.filter((id): id is string => typeof id === "string" && id.length > 0)
    : [];
  return { result: { ok: true, note: call.args.note ?? null }, done: { evidence_ids } };
};

const evidenceFromIds = (input: TreeInputSnapshot, evidenceIds: readonly string[]) => {
  const wanted = new Set(evidenceIds);
  const spans = uniqByEvidenceId(input.evidence_index.filter((span) => wanted.has(span.evidence_id) && span.excerpt));
  const claimIds = input.claims.filter((claim) => claim.evidence_spans.some((span) => wanted.has(span.evidence_id))).map((claim) => claim.claim_revision_id);
  return { spans, claimIds };
};

/** Preserve harvest order; cap only. No soft ranking / domain boosts. */
const takeAccumulated = (evidenceIds: readonly string[], limit: number): string[] => {
  const out: string[] = [];
  for (const id of evidenceIds) {
    if (out.includes(id)) continue;
    out.push(id);
    if (out.length >= limit) break;
  }
  return out;
};

const harvestEvidenceIds = (result: unknown): string[] => {
  if (!result || typeof result !== "object") return [];
  const out: string[] = [];
  const push = (ids: unknown) => {
    if (!Array.isArray(ids)) return;
    for (const id of ids) if (typeof id === "string" && id.length > 0) out.push(id);
  };
  const row = result as Record<string, unknown>;
  if (Array.isArray(row.hits)) for (const hit of row.hits) push((hit as { evidence_ids?: unknown }).evidence_ids);
  if (Array.isArray(row.claims)) for (const claim of row.claims) push((claim as { evidence_ids?: unknown }).evidence_ids);
  push(row.evidence_ids);
  if (Array.isArray(row.excerpts)) for (const ex of row.excerpts) {
    const id = (ex as { evidence_id?: unknown }).evidence_id;
    if (typeof id === "string" && id.length > 0) out.push(id);
  }
  if (Array.isArray(row.surfaces)) for (const surface of row.surfaces) push((surface as { claim_ids?: unknown }).claim_ids);
  return out;
};

const claimIdsToEvidence = (input: TreeInputSnapshot, claimIds: readonly string[]): string[] => {
  const byId = new Map(input.claims.map((claim) => [claim.claim_revision_id, claim]));
  return claimIds.flatMap((id) => byId.get(id)?.evidence_spans.map((span) => span.evidence_id) ?? []);
};

type GroundedAssertion = { text: string; citations: readonly string[] };
type GroundResult = { failures: string[]; entailed: GroundedAssertion[] };

const asSentence = (text: string) => {
  const trimmed = text.trim();
  if (!trimmed) return "";
  return /[.!?]$/u.test(trimmed) ? trimmed : `${trimmed}.`;
};

/** Rebuild answer from entailed assertions only (drop failures; never fluency-smooth). */
const salvageFromEntailed = (entailed: readonly GroundedAssertion[]) => {
  const assertions = entailed
    .map((assertion) => ({ text: asSentence(assertion.text), citations: [...new Set(assertion.citations)].sort() }))
    .filter((assertion) => assertion.text && assertion.citations.length);
  return {
    answer_text: assertions.map((assertion) => assertion.text).join(" "),
    citations: [...new Set(assertions.flatMap((assertion) => assertion.citations))].sort(),
    assertions,
  };
};

const groundCompose = async (
  composed: { answer_text: string; citations: readonly string[]; assertions: readonly { text: string; citations: readonly string[] }[] },
  spans: readonly { evidence_id: string; excerpt: string | null }[],
  model: AgenticModelPort,
): Promise<GroundResult> => {
  const failures: string[] = [];
  const entailed: GroundedAssertion[] = [];
  const permittedCitations = new Set(spans.map((span) => span.evidence_id));
  const normalizedAssertion = (text: string) => text.trim().replace(/[.!?]+$/u, "").replace(/\s+/gu, " ").toLocaleLowerCase();
  const assertionUnits = (text: string) => text.split(/(?<=[.!?])\s+|\n+/u).map((unit) => unit.trim()).filter(Boolean);
  const declaredAssertions = new Set(composed.assertions.map((assertion) => normalizedAssertion(assertion.text)).filter(Boolean));
  for (const unit of assertionUnits(composed.answer_text)) {
    if (!declaredAssertions.has(normalizedAssertion(unit))) failures.push(`answer assertion is absent from grounding manifest: ${unit}`);
  }
  const judgments = await Promise.all(composed.assertions.map(async (assertion) => {
    const cited = assertion.citations.filter((citation) => permittedCitations.has(citation));
    if (!assertion.text || cited.length !== assertion.citations.length || cited.length === 0) return { kind: "uncited" as const };
    const cited_spans = spans.filter((span) => cited.includes(span.evidence_id)).map((span) => ({ evidence_id: span.evidence_id, excerpt: span.excerpt! }));
    return { kind: "judged" as const, cited, judged: await model.invoke({ strategy: "span-entailment", version: "v1", input: { assertion: assertion.text, cited_spans } }) };
  }));
  composed.assertions.forEach((assertion, index) => {
    const outcome = judgments[index]!;
    if (outcome.kind === "uncited") { failures.push(`assertion lacks permitted cited span: ${assertion.text}`); return; }
    if (!(typeof outcome.judged === "object" && outcome.judged !== null && (outcome.judged as { entailed?: unknown }).entailed === true)) {
      failures.push(`cited span does not entail assertion: ${assertion.text}`);
      return;
    }
    entailed.push({ text: assertion.text, citations: outcome.cited });
  });
  if (composed.answer_text && composed.assertions.length === 0) failures.push("non-empty answer has no asserted-claim grounding manifest");
  return { failures, entailed };
};

/**
 * Agentic owner recall: model picks graph tools; host executes on the D46 safe
 * projection + live tree claims. No host query-class packs/seeds. Compose+entailment
 * with drop-only salvage.
 */
export const retrieveAgentic = async (
  request: AgenticRequest,
  graph: GraphSnapshot,
  input: TreeInputSnapshot,
  model: AgenticModelPort,
  model_version = "agentic-recall-v2",
): Promise<DogfoodResponse & { agent_steps: number; agent_trace: readonly { tool: string; args: Record<string, unknown> }[] }> => {
  if (request.owner_account_id !== graph.owner_account_id || request.owner_account_id !== input.owner_account_id) throw new Error("agentic owner does not match snapshot");
  const maxSteps = request.max_steps ?? 12;
  const maxEvidence = request.max_evidence ?? 32;
  const messages: AgenticChatMessage[] = [
    { role: "system", content: AGENTIC_SYSTEM_PROMPT },
    { role: "user", content: JSON.stringify({ question: request.query, live_claims: input.claims.length, note: "Search skips provisional_abstained (dream deferred). Reformulate search yourself. Call done when ready within the step budget." }) },
  ];
  const trace: { tool: string; args: Record<string, unknown> }[] = [];
  const accumulated: string[] = [];
  let selected: string[] = [];

  for (let step = 0; step < maxSteps; step += 1) {
    const call = parseToolCall(await model.agentStep(messages));
    trace.push({ tool: call.tool, args: call.args });
    messages.push({ role: "assistant", content: JSON.stringify(call) });
    const executed = runAgenticTools(input, graph, request, call);
    messages.push({ role: "user", content: JSON.stringify(executed.result) });

    const harvested = harvestEvidenceIds(executed.result);
    const fromClaims = claimIdsToEvidence(input, harvested.filter((id) => !id.startsWith("evidence:") && input.claims.some((c) => c.claim_revision_id === id)));
    const evidenceOnly = harvested.filter((id) => id.startsWith("evidence:") || input.evidence_index.some((span) => span.evidence_id === id));
    for (const id of [...evidenceOnly, ...fromClaims]) if (!accumulated.includes(id)) accumulated.push(id);

    if (executed.done) {
      // selected = done ∪ harvest (capped). Empty done still keeps tool harvest.
      selected = takeAccumulated([...executed.done.evidence_ids, ...accumulated], maxEvidence);
      break;
    }
    if (step === maxSteps - 1) {
      selected = takeAccumulated(accumulated, maxEvidence);
      break;
    }
  }
  if (!selected.length && accumulated.length) selected = takeAccumulated(accumulated, maxEvidence);

  const { spans, claimIds } = evidenceFromIds(input, selected);
  const limited = uniqByEvidenceId(spans).slice(0, maxEvidence);
  if (!limited.length) {
    return { answer_text: null, citations: [], assertions: [], hydrated_claim_revision_ids: [], absence: { kind: "query_gap", message: "no cited memory matched" } satisfies AbsenceDisclosure, grounding: null, agent_steps: trace.length, agent_trace: trace };
  }

  const composeInput = { query: request.query, evidence_spans: limited.map((span) => ({ evidence_id: span.evidence_id, excerpt: span.excerpt })) };
  let composed = await model.compose({ strategy: "citation-grounded-compose", version: model_version, input: composeInput });
  let ground = await groundCompose(composed, limited, model);
  let bestEntailed = ground.entailed;

  if (ground.failures.length) {
    composed = await model.compose({
      strategy: "citation-grounded-compose",
      version: model_version,
      input: { ...composeInput, repair_hint: `Previous answer failed grounding. Fix these failures and cite only the excerpts shown:\n- ${ground.failures.join("\n- ")}` },
    });
    ground = await groundCompose(composed, limited, model);
    if (ground.entailed.length > bestEntailed.length) bestEntailed = ground.entailed;
  }

  const hydrated_claim_revision_ids = [...new Set(claimIds)].sort();
  if (bestEntailed.length) {
    const salvaged = salvageFromEntailed(bestEntailed);
    return {
      answer_text: salvaged.answer_text,
      citations: salvaged.citations,
      assertions: salvaged.assertions,
      hydrated_claim_revision_ids,
      absence: null,
      grounding: { status: "grounded" },
      agent_steps: trace.length,
      agent_trace: trace,
    };
  }
  return {
    answer_text: null,
    citations: [],
    assertions: [],
    hydrated_claim_revision_ids: [],
    absence: { kind: "query_gap", message: "no cited memory matched" } satisfies AbsenceDisclosure,
    grounding: null,
    agent_steps: trace.length,
    agent_trace: trace,
  };
};
