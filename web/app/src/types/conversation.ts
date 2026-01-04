/**
 * Conversation types matching the backend API schema
 * Reference: /backend/routers/conversations.py
 */

export type ConversationStatus = 'in_progress' | 'processing' | 'merging' | 'completed' | 'failed';

export interface Structured {
  title: string;
  emoji: string;
  overview: string;
  category: string;
  action_items?: ActionItem[];
  events?: Event[];
}

export interface ActionItem {
  id: string;
  description: string;
  completed: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  due_at?: string | null;
  completed_at?: string | null;
  conversation_id?: string | null;
}

/**
 * Grouped action items by time period
 */
export interface GroupedActionItems {
  overdue: ActionItem[];
  today: ActionItem[];
  tomorrow: ActionItem[];
  thisWeek: ActionItem[];
  later: ActionItem[];
  noDueDate: ActionItem[];
  completed: ActionItem[];
}

export interface Event {
  title: string;
  start: string;
  duration: number;
  description?: string;
}

export interface TranscriptSegment {
  id?: string;
  text: string;
  speaker: string;
  speaker_id: number;
  is_user: boolean;
  person_id?: string | null;
  speaker_name?: string; // Added by MCP endpoint or resolved client-side
  start: number;
  end: number;
}

export interface Geolocation {
  latitude: number;
  longitude: number;
  address?: string | null;
  google_place_id?: string | null;
  location_type?: string | null;
}

export interface ConversationPhoto {
  base64: string;
  description?: string;
}

export interface AudioFile {
  id?: string;
  url?: string;
  chunk_start?: number;
  chunk_end?: number;
  duration?: number;
  signed_url?: string | null;
}

export interface AudioFileUrlInfo {
  id: string;
  status: 'cached' | 'pending';
  signed_url: string | null;
  duration: number;
}

export interface AppResponse {
  app_id: string;
  content: string;
}

export interface Conversation {
  id: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  structured: Structured;
  transcript_segments: TranscriptSegment[];
  geolocation: Geolocation | null;
  photos: ConversationPhoto[];
  audio_files: AudioFile[];
  apps_results: AppResponse[];  // Note: backend uses 'apps_results' (with 's')
  suggested_summarization_apps: string[];
  source: string | null;
  language: string | null;
  external_integration: Record<string, unknown> | null;
  status: ConversationStatus;
  discarded: boolean;
  deleted: boolean;
  is_locked: boolean;
  starred: boolean;
  folder_id: string | null;
}

/**
 * Paginated search response
 */
export interface ConversationSearchResponse {
  items: Conversation[];
  current_page: number;
  total_pages: number;
}

/**
 * Grouped conversations by date
 */
export interface GroupedConversations {
  [dateKey: string]: Conversation[];
}

// =============================================================================
// Memory Types
// =============================================================================

export type MemoryCategory = 'interesting' | 'system' | 'manual';
export type MemoryVisibility = 'public' | 'private';

export interface Memory {
  id: string;
  uid: string;
  content: string;
  category: MemoryCategory;
  visibility: MemoryVisibility;
  tags: string[];
  created_at: string;
  updated_at: string;
  memory_id?: string | null;
  conversation_id?: string | null;
  reviewed: boolean;
  user_review?: boolean | null;
  manually_added: boolean;
  edited: boolean;
  deleted?: boolean;
  scoring?: string;
  app_id?: string | null;
  data_protection_level?: string;
  is_locked: boolean;
  kg_extracted?: boolean;
}

// =============================================================================
// Knowledge Graph Types
// =============================================================================

export type KnowledgeGraphNodeType = 'person' | 'place' | 'organization' | 'thing' | 'concept';

export interface KnowledgeGraphNode {
  id: string;
  label: string;
  node_type: KnowledgeGraphNodeType;
  aliases: string[];
  memory_ids: string[];
}

export interface KnowledgeGraphEdge {
  id: string;
  source_id: string;
  target_id: string;
  label: string;
  memory_ids: string[];
}

export interface KnowledgeGraph {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

// =============================================================================
// Chat/Message Types (matching mobile app schema)
// =============================================================================

export type MessageSender = 'ai' | 'human';
export type MessageType = 'text' | 'day_summary';
export type MessageChunkType = 'think' | 'data' | 'done' | 'message' | 'error';

export interface MessageFile {
  id: string;
  openai_file_id: string;
  thumbnail?: string | null;
  thumbnail_name?: string | null;
  name: string;
  mime_type: string;
  created_at: string;
}

export interface MessageMemory {
  id: string;
  structured: {
    title: string;
    emoji: string;
  };
}

export interface ServerMessage {
  id: string;
  created_at: string;
  text: string;
  sender: MessageSender;
  type: MessageType;
  plugin_id?: string | null;  // app_id for routing
  from_integration: boolean;
  files: MessageFile[];
  memories: MessageMemory[];
  ask_for_nps: boolean;
}

export interface MessageChunk {
  type: MessageChunkType;
  text: string;
  message?: ServerMessage;
}

export interface SendMessageRequest {
  text: string;
  file_ids?: string[];
}
