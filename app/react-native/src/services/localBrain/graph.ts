import type { BrainEdge, BrainEdgeType, BrainNode, BrainNodeType, EvidenceRef, KnowledgeGraph } from './types';

function nowMs() {
  return Date.now();
}

function id(prefix: string) {
  return `${prefix}_${nowMs().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function upsertNode(
  graph: KnowledgeGraph,
  input: {
    id?: string;
    type: BrainNodeType;
    label: string;
    content?: string;
    confidence?: number;
    status?: BrainNode['status'];
    source?: BrainNode['source'];
    evidence?: EvidenceRef[];
    meta?: BrainNode['meta'];
    pinned?: boolean;
  }
): BrainNode {
  const existing = input.id ? graph.nodes[input.id] : undefined;
  const node: BrainNode = {
    id: input.id ?? existing?.id ?? id(`n_${input.type}`),
    type: input.type,
    label: input.label,
    content: input.content ?? existing?.content,
    createdAt: existing?.createdAt ?? nowMs(),
    updatedAt: nowMs(),
    confidence: input.confidence ?? existing?.confidence ?? 0.7,
    status: input.status ?? existing?.status ?? 'active',
    pinned: input.pinned ?? existing?.pinned,
    source: input.source ?? existing?.source ?? 'pipeline',
    evidence: mergeEvidence(existing?.evidence ?? [], input.evidence ?? []),
    meta: { ...(existing?.meta ?? {}), ...(input.meta ?? {}) },
  };
  graph.nodes[node.id] = node;
  return node;
}

export function upsertEdge(
  graph: KnowledgeGraph,
  input: {
    id?: string;
    type: BrainEdgeType;
    from: string;
    to: string;
    confidence?: number;
    evidence?: EvidenceRef[];
  }
): BrainEdge | null {
  if (!graph.nodes[input.from] || !graph.nodes[input.to]) return null;
  const existing = input.id
    ? graph.edges[input.id]
    : Object.values(graph.edges).find((e) => e.type === input.type && e.from === input.from && e.to === input.to);
  const edge: BrainEdge = {
    id: existing?.id ?? input.id ?? id(`e_${input.type}`),
    type: input.type,
    from: input.from,
    to: input.to,
    createdAt: existing?.createdAt ?? nowMs(),
    confidence: input.confidence ?? existing?.confidence ?? 0.7,
    evidence: mergeEvidence(existing?.evidence ?? [], input.evidence ?? []),
  };
  graph.edges[edge.id] = edge;
  return edge;
}

export function mergeEvidence(a: EvidenceRef[], b: EvidenceRef[]): EvidenceRef[] {
  const out = [...a];
  for (const ev of b) {
    const key = `${ev.conversationId ?? ''}|${ev.segmentId ?? ''}|${ev.text ?? ''}`;
    if (!out.some((x) => `${x.conversationId ?? ''}|${x.segmentId ?? ''}|${x.text ?? ''}` === key)) {
      out.push(ev);
    }
  }
  return out.slice(-8);
}

export function nodeIdForConversation(conversationId: string) {
  return `conv:${conversationId}`;
}
export function nodeIdForSummary(conversationId: string) {
  return `sum:${conversationId}`;
}
export function nodeIdForMemory(memoryId: string) {
  return `mem:${memoryId}`;
}
export function nodeIdForTask(taskId: string) {
  return `task:${taskId}`;
}
export function nodeIdForTopic(topic: string) {
  return `topic:${topic.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 48)}`;
}

export function getGraphStats(graph: KnowledgeGraph) {
  const nodes = Object.values(graph.nodes).filter((n) => n.status !== 'forgotten');
  const edges = Object.values(graph.edges);
  const byType: Record<string, number> = {};
  for (const n of nodes) byType[n.type] = (byType[n.type] ?? 0) + 1;
  return { nodeCount: nodes.length, edgeCount: edges.length, byType };
}
