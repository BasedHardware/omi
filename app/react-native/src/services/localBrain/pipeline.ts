import { getConversation, listConversations, type StoredConversation } from '../localConversations';
import { extractiveSummarize, extractMemories, extractTasks } from './extractors';
import { nodeIdForConversation, nodeIdForMemory, nodeIdForSummary, nodeIdForTask, nodeIdForTopic, upsertEdge, upsertNode } from './graph';
import { loadBrainState, updateBrainState } from './storage';
import type { LocalBrainState } from './types';

function nowMs() {
  return Date.now();
}

type Keyed = { id: string; text?: string; title?: string; createdAt?: number; updatedAt?: number };

function mergeByText<T extends Keyed>(existing: Record<string, T>, incoming: T[], keyOf: (x: T) => string): Record<string, T> {
  const out = { ...existing };
  const existingKeys = new Map<string, string>();
  for (const [id, v] of Object.entries(out)) existingKeys.set(keyOf(v), id);
  for (const item of incoming) {
    const k = keyOf(item);
    const prevId = existingKeys.get(k);
    if (prevId && out[prevId]) {
      const prev = out[prevId];
      out[prevId] = { ...prev, ...item, id: prevId, createdAt: prev.createdAt ?? item.createdAt, updatedAt: nowMs() };
    } else {
      out[item.id] = item;
      existingKeys.set(k, item.id);
    }
  }
  return out;
}

function ensureConversationNode(state: LocalBrainState, convo: StoredConversation) {
  const cNode = upsertNode(state.graph, {
    id: nodeIdForConversation(convo.id),
    type: 'conversation',
    label: convo.title || `Conversation ${new Date(convo.startedAt).toLocaleString()}`,
    content: convo.segments.slice(0, 3).map((s) => s.text).join(' '),
    confidence: 1,
    source: 'system',
    evidence: [{ conversationId: convo.id, startedAt: convo.startedAt }],
    meta: { source: convo.source, startedAt: convo.startedAt },
  });
  return cNode;
}

export async function processConversation(conversationId: string): Promise<LocalBrainState> {
  const convo = await getConversation(conversationId);
  if (!convo) return loadBrainState();
  return processConversationObject(convo);
}

export async function processConversationObject(convo: StoredConversation): Promise<LocalBrainState> {
  return updateBrainState((state) => {
    // Primary per-conversation artifact: extractive summary grounded in this session's transcript.
    const summary = extractiveSummarize(convo);
    state.summaries[summary.id] = summary;

    // Derive memories from the conversation's summary (scoped to this session) with evidence links.
    const mems = extractMemories(convo, summary);
    state.memories = mergeByText(state.memories, mems, (m) => `${m.kind}|${String(m.text).toLowerCase().slice(0, 80)}`);

    // Derive tasks/action items from this conversation (summary-first).
    const tasks = extractTasks(convo, summary);
    state.tasks = mergeByText(state.tasks, tasks, (t) => `${t.kind}|${String(t.title).toLowerCase()}`);

    // profile signals: collect preference/routine memories into profile (bounded)
    const prefTexts = Object.values(state.memories)
      .filter((m) => m.status === 'active' && (m.kind === 'preference' || m.kind === 'routine' || m.kind === 'commitment'))
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, 12)
      .map((m) => m.text);
    state.profile = {
      ...state.profile,
      updatedAt: nowMs(),
      preferences: prefTexts.filter((t) => /\b(prefer|like|love|favorite)\b/i.test(t)).slice(0, 8),
      routines: prefTexts.filter((t) => /\b(always|usually|often|routine|every)\b/i.test(t)).slice(0, 8),
      evidence: [...(state.profile.evidence ?? []), ...summary.evidence.slice(0, 2)].slice(-12),
    };

    // graph
    const cNode = ensureConversationNode(state, convo);
    const sNode = upsertNode(state.graph, {
      id: nodeIdForSummary(convo.id),
      type: 'summary',
      label: summary.highlights[0]?.slice(0, 60) || `Summary: ${convo.title || convo.id}`,
      content: summary.highlights.join('\n'),
      confidence: 0.75,
      source: 'pipeline',
      evidence: summary.evidence,
      meta: { conversationId: convo.id },
    });
    upsertEdge(state.graph, { type: 'derived_from', from: sNode.id, to: cNode.id, confidence: 0.95, evidence: summary.evidence });

    for (const topic of summary.topics) {
      const tNode = upsertNode(state.graph, {
        id: nodeIdForTopic(topic),
        type: 'topic',
        label: topic,
        confidence: 0.7,
        source: 'pipeline',
      });
      upsertEdge(state.graph, { type: 'about', from: cNode.id, to: tNode.id, confidence: 0.65, evidence: summary.evidence.slice(0, 2) });
      upsertEdge(state.graph, { type: 'about', from: sNode.id, to: tNode.id, confidence: 0.65, evidence: summary.evidence.slice(0, 2) });
    }

    for (const mem of Object.values(state.memories)) {
      // only link memories that cite this conversation
      if (!mem.evidence.some((e) => e.conversationId === convo.id)) continue;
      const mNode = upsertNode(state.graph, {
        id: nodeIdForMemory(mem.id),
        type: mem.kind === 'preference' ? 'preference' : mem.kind === 'routine' ? 'routine' : mem.kind === 'commitment' ? 'commitment' : 'memory',
        label: mem.text.slice(0, 60),
        content: mem.text,
        confidence: mem.confidence,
        source: 'pipeline',
        status: mem.status === 'forgotten' ? 'forgotten' : 'active',
        evidence: mem.evidence,
        meta: { memoryId: mem.id, kind: mem.kind },
      });
      upsertEdge(state.graph, { type: 'derived_from', from: mNode.id, to: cNode.id, confidence: mem.confidence, evidence: mem.evidence });
      for (const tag of mem.tags.slice(0, 3)) {
        const tNode = upsertNode(state.graph, { id: nodeIdForTopic(tag), type: 'topic', label: tag, source: 'pipeline' });
        upsertEdge(state.graph, { type: 'mentions', from: mNode.id, to: tNode.id, confidence: 0.6, evidence: mem.evidence.slice(0, 1) });
      }
    }

    for (const task of Object.values(state.tasks)) {
      if (!task.evidence.some((e) => e.conversationId === convo.id)) continue;
      const tNode = upsertNode(state.graph, {
        id: nodeIdForTask(task.id),
        type: 'task',
        label: task.title.slice(0, 60),
        content: task.title,
        confidence: 0.75,
        source: 'pipeline',
        status: task.status === 'done' ? 'done' : 'active',
        evidence: task.evidence,
        meta: { taskId: task.id, kind: task.kind, dueAt: task.dueAt ?? null },
      });
      upsertEdge(state.graph, { type: 'derived_from', from: tNode.id, to: cNode.id, confidence: 0.8, evidence: task.evidence });
    }

    state.processing.processedConversationIds[convo.id] = nowMs();
    state.processing.lastRunAt = nowMs();
  });
}

export async function processUnprocessedConversations(limit = 10): Promise<LocalBrainState> {
  const state = await loadBrainState();
  const convos = await listConversations(); // newest first
  const pending = convos
    .filter((c) => !state.processing.processedConversationIds[c.id])
    .slice(0, limit)
    .reverse(); // process older->newer
  let current = state;
  for (const c of pending) {
    current = await processConversationObject(c);
  }
  return current;
}

export async function reprocessRecent(limit = 5): Promise<LocalBrainState> {
  const convos = await listConversations();
  let current = await loadBrainState();
  for (const c of convos.slice(0, limit)) {
    current = await processConversationObject(c);
  }
  return current;
}
