/**
 * Conversation / memory / message / knowledge-graph types.
 *
 * Schema authority for backend REST DTOs lives in `@/lib/omiApi.generated.ts`,
 * generated from `docs/api-reference/app-client-openapi.json`. This file only
 * re-exports those generated types under the names the rest of the app imports,
 * plus behavior-only adapters (grouping, SSE streaming, client UI state) that
 * are not backend schema.
 *
 * Drift note: the previous hand-written `ServerMessage` used `from_integration`
 * and `plugin_id`. Backend Pydantic (`backend/models/chat.py` `Message`) is
 * authority and exposes `from_external_integration` plus both `app_id` and
 * `plugin_id` (kept in sync by `_sync_app_and_plugin_ids`). Generated `Message`
 * mirrors that authority; consumers should use `from_external_integration` and
 * `app_id` for new code. `MessageChunk`/`MessageChunkType` describe the SSE
 * streaming protocol (out of REST scope) and remain local types.
 */

export type {
  AppResult,
  AudioFile,
  AudioFileUrlInfo,
  Conversation,
  ConversationPhoto,
  ConversationStatus,
  Event,
  Geolocation,
  MemoryCategory,
  Structured,
} from '@/lib/omiApi.generated';

// `Memory` and `TranscriptSegment` aliases are defined below as intersections
// because consumers read client-enriched fields the backend REST schema does
// not expose (MemoryDB is the REST shape; speaker_name is client-computed).
export type { MemoryDB as Memory } from '@/lib/omiApi.generated';

import type {
  ActionItemResponse,
  AppResult,
  Conversation as GeneratedConversation,
} from '@/lib/omiApi.generated';
import type { ActionItem as GeneratedActionItem } from '@/lib/omiApi.generated';
import type {
  FileChat,
  Message,
  MessageSender,
  MessageType,
  TranscriptSegment as GeneratedTranscriptSegment,
} from '@/lib/omiApi.generated';

/**
 * Legacy alias for the generated `AppResult` schema (backend
 * `AppResult` Pydantic model). Both expose `app_id` + `content`.
 */
export type AppResponse = import('@/lib/omiApi.generated').AppResult;

/**
 * `ActionItem` is the legacy alias for the generated `ActionItemResponse`
 * schema — the backend REST authority for `/v1/action-items`. The structured
 * `ActionItem` model embedded in `Conversation.structured.action_items` is a
 * subset (no `id`), but the tasks UI always reads from the standalone endpoint,
 * so this alias carries the full standalone shape including `id`.
 */
export type ActionItem = ActionItemResponse;

/** Keep the generated structured ActionItem shape reachable for documentation. */
export type StructuredActionItem = GeneratedActionItem;

/**
 * Transcript segment as consumed by the renderer. The generated
 * `TranscriptSegment` is the backend REST authority; `speaker_name` is a
 * client-computed display field (resolved from people/speaker_id) that the
 * backend model does not expose.
 */
export type TranscriptSegment = GeneratedTranscriptSegment & {
  speaker_name?: string;
};

/**
 * Memory visibility. The backend `Memory.visibility` Pydantic field is typed
 * as `str` (default `'private'`), so it does not surface as an enum in the
 * generated schema. This union is the client-side constraint used by the UI
 * toggle and matches the values the backend accepts.
 */
export type MemoryVisibility = 'public' | 'private';

/**
 * Grouped action items by time period. Client-side view model over the
 * generated `ActionItem` schema.
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

/**
 * Paginated search response. The backend `/v1/conversations/search` route
 * returns raw Typesense docs as loose maps, so the generated
 * `SearchConversationsResponse` types `items` as `Array<Record<string, unknown>>`.
 * This adapter re-types items as `Conversation[]` for app consumers; the field
 * set is the same `Conversation` schema authority.
 */
export interface ConversationSearchResponse {
  items: GeneratedConversation[];
  current_page: number;
  total_pages: number;
}

/**
 * Grouped conversations by date. Client-side view model.
 */
export interface GroupedConversations {
  [dateKey: string]: GeneratedConversation[];
}

// =============================================================================
// Knowledge Graph Types
// =============================================================================
// The backend `/v1/knowledge-graph` route returns `KnowledgeGraphResponse`
// with `nodes`/`edges` typed as `Array<Record<string, unknown>>` (loose maps).
// Until the backend exposes typed node/edge schemas, these local types describe
// the shape the app renders. They are NOT backend schema authority.

export type KnowledgeGraphNodeType =
  'person' | 'place' | 'organization' | 'thing' | 'concept';

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
// Chat / Message Types
// =============================================================================

export type { MessageSender, MessageType } from '@/lib/omiApi.generated';

/**
 * `MessageFile` is the legacy alias for the generated `FileChat` schema
 * (backend `FileChat` Pydantic model). `thumbnail_name` -> `thumb_name` is the
 * only rename; both map to the same backend field.
 */
export type MessageFile = FileChat;

/**
 * `MessageMemory` matches the generated `MessageConversation` schema exactly.
 */
export type { MessageConversation as MessageMemory } from '@/lib/omiApi.generated';

/**
 * `ServerMessage` is the legacy alias for the generated `Message` schema —
 * the backend REST authority for chat messages. Use `Message` in new code.
 */
export type ServerMessage = Message;

/**
 * Streaming SSE chunk shape (NOT a REST DTO). The `/v2/messages` streaming
 * protocol emits these chunks; out of scope for OpenAPI REST SSoT.
 */
export type MessageChunkType = 'think' | 'data' | 'done' | 'message' | 'error';

export interface MessageChunk {
  type: MessageChunkType;
  text: string;
  message?: ServerMessage;
}

/**
 * Optimistic client-side message state for the chat UI. Distinct from
 * `ServerMessage`/`Message` because it carries UI-only fields
 * (`ask_for_nps`) that the backend REST schema does not expose.
 */
export interface ClientMessage extends ServerMessage {
  ask_for_nps?: boolean;
}

/**
 * Request body for `POST /v2/messages`. Matches generated `SendMessageRequest`.
 */
export type { SendMessageRequest } from '@/lib/omiApi.generated';
