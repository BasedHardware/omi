import { searchLocal, type SearchHit } from '../localConversations';
import { loadBrainState } from './storage';
import type { EvidenceRef, LocalMemory, LocalTask } from './types';

export interface BrainEvidence {
  kind: 'segment' | 'summary' | 'memory' | 'task';
  text: string;
  score?: number;
  ref: EvidenceRef;
}

export interface RetrievedContext {
  query: string;
  hits: SearchHit[];
  memories: LocalMemory[];
  tasks: LocalTask[];
  summaries: Array<{ conversationId: string; highlights: string[]; evidence: EvidenceRef[] }>;
  evidence: BrainEvidence[];
}

const CONTEXT_BUDGET = {
  maxHits: 4,
  maxMemories: 3,
  maxTasks: 3,
  maxSummaries: 2,
  maxHighlightsPerSummary: 2,
  maxEvidence: 8,
  maxSnippetChars: 180,
  maxContextChars: 1400,
} as const;

function scoreText(qTerms: string[], text: string): number {
  const hay = text.toLowerCase();
  let m = 0;
  for (const t of qTerms) if (hay.includes(t)) m++;
  return qTerms.length ? m / qTerms.length : 0;
}

function qTerms(query: string): string[] {
  return query.toLowerCase().replace(/[^a-z0-9\s']/g, ' ').split(/\s+/).filter((t) => t.length > 2);
}

function clip(text: string, max: number = CONTEXT_BUDGET.maxSnippetChars): string {
  const t = text.trim().replace(/\s+/g, ' ');
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

export async function retrieveContext(
  query: string,
  opts: { speaker?: string; limit?: number } = {}
): Promise<RetrievedContext> {
  const limit = Math.min(opts.limit ?? CONTEXT_BUDGET.maxHits, CONTEXT_BUDGET.maxHits);
  const terms = qTerms(query);
  const hits = (await searchLocal(query, { speaker: opts.speaker, limit })).map((h) => ({
    ...h,
    text: clip(h.text),
  }));
  const state = await loadBrainState();

  const memories = Object.values(state.memories)
    .filter((m) => m.status === 'active')
    .map((m) => ({ m, s: scoreText(terms, m.text) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || b.m.updatedAt - a.m.updatedAt)
    .slice(0, CONTEXT_BUDGET.maxMemories)
    .map((x) => ({ ...x.m, text: clip(x.m.text) }));

  const tasks = Object.values(state.tasks)
    .filter((t) => t.status === 'open')
    .map((t) => ({ t, s: scoreText(terms, t.title) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || b.t.updatedAt - a.t.updatedAt)
    .slice(0, CONTEXT_BUDGET.maxTasks)
    .map((x) => ({ ...x.t, title: clip(x.t.title, 120) }));

  const convoIds = new Set(hits.map((h) => h.conversationId));
  const summaries = Object.values(state.summaries)
    .filter((s) => convoIds.has(s.conversationId) || scoreText(terms, s.highlights.join(' ')) > 0)
    .slice(0, CONTEXT_BUDGET.maxSummaries)
    .map((s) => ({
      conversationId: s.conversationId,
      highlights: s.highlights.slice(0, CONTEXT_BUDGET.maxHighlightsPerSummary).map((h) => clip(h)),
      evidence: s.evidence.slice(0, 2),
    }));

  const evidence: BrainEvidence[] = [];
  for (const h of hits.slice(0, 3)) {
    evidence.push({
      kind: 'segment',
      text: clip(`${h.speaker}: "${h.text}"`),
      score: h.score,
      ref: { conversationId: h.conversationId, segmentId: h.segmentId, text: h.text, speaker: h.speaker, startedAt: h.startedAt },
    });
  }
  for (const m of memories.slice(0, 2)) {
    evidence.push({ kind: 'memory', text: clip(`Remembered: ${m.text}`), ref: m.evidence[0] ?? {} });
  }
  for (const t of tasks.slice(0, 2)) {
    evidence.push({ kind: 'task', text: clip(`Open ${t.kind}: ${t.title}`), ref: t.evidence[0] ?? {} });
  }
  for (const s of summaries.slice(0, 1)) {
    if (s.highlights[0]) evidence.push({ kind: 'summary', text: clip(`Summary: ${s.highlights[0]}`), ref: s.evidence[0] ?? { conversationId: s.conversationId } });
  }

  return {
    query,
    hits,
    memories,
    tasks,
    summaries,
    evidence: evidence.slice(0, CONTEXT_BUDGET.maxEvidence),
  };
}

export function formatContextForAnswer(ctx: RetrievedContext): string {
  const lines: string[] = [];
  const push = (line: string) => {
    const next = [...lines, line].join('\n');
    if (next.length <= CONTEXT_BUDGET.maxContextChars) lines.push(line);
  };

  if (ctx.hits.length) {
    push('Evidence from recordings:');
    for (const h of ctx.hits.slice(0, 3)) push(`- ${clip(`${h.speaker}: "${h.text}"`, 140)}`);
  }
  if (ctx.summaries.length) {
    push('Related summary highlights:');
    for (const s of ctx.summaries.slice(0, CONTEXT_BUDGET.maxSummaries)) {
      for (const hl of s.highlights.slice(0, CONTEXT_BUDGET.maxHighlightsPerSummary)) push(`- ${clip(hl, 140)}`);
    }
  }
  if (ctx.memories.length) {
    push('Related memories:');
    for (const m of ctx.memories.slice(0, 2)) push(`- ${clip(m.text, 140)}`);
  }
  if (ctx.tasks.length) {
    push('Related open tasks:');
    for (const t of ctx.tasks.slice(0, 2)) push(`- ${clip(t.title, 120)}`);
  }

  let out = lines.join('\n');
  if (out.length > CONTEXT_BUDGET.maxContextChars) out = `${out.slice(0, CONTEXT_BUDGET.maxContextChars - 1)}…`;
  return out;
}

export function getContextBudget() {
  return { ...CONTEXT_BUDGET };
}
