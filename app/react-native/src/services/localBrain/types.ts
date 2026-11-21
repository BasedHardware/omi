import type { CaptureSource } from '../localConversations';

export type BrainNodeType =
  | 'conversation'
  | 'segment'
  | 'summary'
  | 'memory'
  | 'task'
  | 'person'
  | 'topic'
  | 'preference'
  | 'routine'
  | 'commitment'
  | 'profile_trait';

export type BrainEdgeType =
  | 'derived_from'
  | 'mentions'
  | 'about'
  | 'supports'
  | 'contradicts'
  | 'supersedes'
  | 'follow_up_to'
  | 'scheduled_as'
  | 'related_to';

export interface EvidenceRef {
  conversationId?: string;
  segmentId?: string;
  text?: string;
  speaker?: string;
  startedAt?: number;
}

export interface BrainNode {
  id: string;
  type: BrainNodeType;
  label: string;
  /** Optional longer content/value. */
  content?: string;
  createdAt: number;
  updatedAt: number;
  confidence: number; // 0..1
  status: 'active' | 'corrected' | 'superseded' | 'forgotten' | 'done';
  pinned?: boolean;
  source: 'pipeline' | 'user' | 'system';
  evidence: EvidenceRef[];
  meta?: Record<string, string | number | boolean | null>;
}

export interface BrainEdge {
  id: string;
  type: BrainEdgeType;
  from: string;
  to: string;
  createdAt: number;
  confidence: number;
  evidence: EvidenceRef[];
}

export interface ExtractiveSummary {
  id: string;
  conversationId: string;
  createdAt: number;
  highlights: string[];
  decisions: string[];
  actionables: string[];
  topics: string[];
  evidence: EvidenceRef[];
}

export interface LocalMemory {
  id: string;
  kind: 'preference' | 'fact' | 'commitment' | 'routine' | 'topic' | 'person';
  text: string;
  createdAt: number;
  updatedAt: number;
  confidence: number;
  status: 'active' | 'corrected' | 'forgotten';
  evidence: EvidenceRef[];
  tags: string[];
}

export interface LocalTask {
  id: string;
  title: string;
  kind: 'task' | 'reminder';
  createdAt: number;
  updatedAt: number;
  dueAt?: number | null;
  remindAt?: number | null;
  status: 'open' | 'done' | 'snoozed' | 'cancelled';
  source: CaptureSource | 'agent' | 'user';
  evidence: EvidenceRef[];
}

export interface PersonalityProfile {
  updatedAt: number;
  traits: string[];
  preferences: string[];
  style: string[];
  boundaries: string[];
  routines: string[];
  evidence: EvidenceRef[];
}

export interface ProcessingState {
  version: number;
  processedConversationIds: Record<string, number>; // id -> processedAt
  lastRunAt?: number;
}

export interface KnowledgeGraph {
  nodes: Record<string, BrainNode>;
  edges: Record<string, BrainEdge>;
}

export interface LocalBrainState {
  schemaVersion: number;
  summaries: Record<string, ExtractiveSummary>;
  memories: Record<string, LocalMemory>;
  tasks: Record<string, LocalTask>;
  profile: PersonalityProfile;
  graph: KnowledgeGraph;
  processing: ProcessingState;
}
