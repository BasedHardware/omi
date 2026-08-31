import { getIdToken } from './firebase';
import { getWebDeviceIdHash } from './clientDevice';
import {
  invalidateCache,
  invalidateCacheKey,
  invalidationPatterns,
  fetchWithCache,
  cacheKeys,
  CACHE_TTL,
} from './cache';
import type {
  Conversation,
  ConversationSearchResponse,
  ConversationScreenFrameSet,
  ConversationStatus,
  ActionItem,
  Memory,
  MemoryCategory,
  MemoryVisibility,
  KnowledgeGraph,
  ScreenFrameSharingUpdateRequest,
  ServerMessage,
  MessageChunk,
  MessageChunkType,
  MessageFile,
  AudioFileUrlInfo,
} from '@/types/conversation';
// Generated REST response envelopes (backend OpenAPI authority).
import type {
  MergeConversationsResponse,
  CreateConversationResponse,
  ActionItemsResponse,
  FairUseStatusResponse,
} from './omiApi.generated';
import {
  normalizeKnowledgeLedgerMemories,
  normalizeKnowledgeLedgerMemory,
} from './knowledgeLedger';
export type {
  MergeConversationsResponse,
  CreateConversationResponse,
  ActionItemsResponse,
};
import type { Goal, GoalHistoryEntry } from '@/types/goals';
import type { ChatSession } from '@/types/chatSessions';
import type { Scores } from '@/types/scores';
import type {
  App,
  AppCategory,
  AppCapability,
  AppsGroupedResponse,
  AppsSearchResponse,
  AppsSearchParams,
  CreateAppRequest,
  UpdateAppRequest,
  ThumbnailUploadResponse,
  GenerateDescriptionResponse,
  NotificationScope,
  PaymentPlan,
} from '@/types/apps';

// Always use proxy to avoid CORS (browser → proxy → api.omi.me)
const API_BASE_URL = '/api/proxy';

/**
 * Make an authenticated API request
 */
async function fetchWithAuth<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const url = `${API_BASE_URL}${endpoint}`;
  const deviceIdHash = await getWebDeviceIdHash();
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  // FormData must set its own Content-Type so fetch can add the multipart
  // boundary; forcing application/json here produces a body the server cannot
  // parse.
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  new Headers(options.headers).forEach((value, name) => headers.set(name, value));
  headers.set('X-App-Platform', 'web');
  if (deviceIdHash) {
    headers.set('X-Device-Id-Hash', deviceIdHash);
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'No error body');
      // Only log non-404 errors (404s are expected for optional endpoints)
      if (response.status !== 404) {
        console.error('API error response:', response.status, errorText);
      }

      if (response.status === 401) {
        throw new Error('Unauthorized - please sign in again');
      }
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    // Handle 204 No Content responses (common for DELETE operations)
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  } catch (fetchError) {
    if (fetchError instanceof TypeError && fetchError.message === 'Failed to fetch') {
      console.error('Network error - possible CORS issue or API unavailable');
      throw new Error(
        'Network error: Unable to reach the API. Please check your connection.',
      );
    }
    throw fetchError;
  }
}

/**
 * Get conversations list with optional filters
 */
export interface GetConversationsParams {
  limit?: number;
  offset?: number;
  statuses?: ConversationStatus[];
  includeDiscarded?: boolean;
  startDate?: Date;
  endDate?: Date;
  folderId?: string;
}

export async function getConversations(
  params: GetConversationsParams = {},
): Promise<Conversation[]> {
  const {
    limit = 50,
    offset = 0,
    statuses = ['processing', 'completed'],
    includeDiscarded = false,
    startDate,
    endDate,
    folderId,
  } = params;

  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
    include_discarded: includeDiscarded.toString(),
    statuses: statuses.join(','),
  });

  if (startDate) {
    queryParams.set('start_date', startDate.toISOString());
  }

  if (endDate) {
    queryParams.set('end_date', endDate.toISOString());
  }

  if (folderId) {
    queryParams.set('folder_id', folderId);
  }

  return fetchWithAuth<Conversation[]>(`/v1/conversations?${queryParams}`);
}

/**
 * Get a single conversation by ID
 * Uses centralized cache with request deduplication
 */
export async function getConversation(id: string): Promise<Conversation> {
  return fetchWithCache<Conversation>(
    cacheKeys.conversation(id),
    () => fetchWithAuth<Conversation>(`/v1/conversations/${id}`),
    { ttl: CACHE_TTL.SHORT },
  );
}

/**
 * Search conversations
 */
export interface SearchConversationsParams {
  query: string;
  page?: number;
  perPage?: number;
  includeDiscarded?: boolean;
}

export async function searchConversations(
  params: SearchConversationsParams,
): Promise<ConversationSearchResponse> {
  const { query, page = 1, perPage = 10, includeDiscarded = false } = params;

  return fetchWithAuth<ConversationSearchResponse>('/v1/conversations/search', {
    method: 'POST',
    body: JSON.stringify({
      query,
      page,
      per_page: perPage,
      include_discarded: includeDiscarded,
    }),
  });
}

/**
 * Toggle conversation starred status
 */
export async function toggleStarred(id: string, starred: boolean): Promise<void> {
  await fetchWithAuth(`/v1/conversations/${id}/starred?starred=${starred}`, {
    method: 'PATCH',
  });
  invalidateCache(invalidationPatterns.conversations);
}

/**
 * Delete a conversation
 */
export async function deleteConversation(id: string): Promise<void> {
  await fetchWithAuth(`/v1/conversations/${id}`, {
    method: 'DELETE',
  });
  invalidateCache(invalidationPatterns.conversations);
}

// =============================================================================
// Meeting-note screenshots ("screen frames")
// =============================================================================
// Types come from the generated OpenAPI client (`@/types/conversation`
// re-exports them). Route paths mirror the shared contract
// (`data/reports/meeting-screenshots/DESIGN-sol.md` §1-2) exactly.

/**
 * Get the approved screenshot set (banner + strip) for a conversation.
 * Uses the same fetch-with-cache idiom as `getConversation`; a short TTL
 * balances against the frame set's signed URLs expiring after 60 minutes.
 */
export async function getConversationScreenFrames(
  conversationId: string,
): Promise<ConversationScreenFrameSet> {
  return fetchWithCache<ConversationScreenFrameSet>(
    cacheKeys.screenFrames(conversationId),
    () =>
      fetchWithAuth<ConversationScreenFrameSet>(
        `/v1/conversations/${conversationId}/screenshots`,
      ),
    { ttl: CACHE_TTL.SHORT },
  );
}

/**
 * Delete a single screenshot. The server may promote another already-
 * approved, already-persisted frame to banner (contract §8); the returned
 * set is authoritative, so callers should replace their local state with it
 * rather than trying to predict the promotion.
 */
export async function deleteScreenFrame(
  conversationId: string,
  frameId: string,
): Promise<ConversationScreenFrameSet> {
  const result = await fetchWithAuth<ConversationScreenFrameSet>(
    `/v1/conversations/${conversationId}/screenshots/${frameId}`,
    { method: 'DELETE' },
  );
  invalidateCacheKey(cacheKeys.screenFrames(conversationId));
  return result;
}

/** Delete every screenshot for a conversation (banner + strip). */
export async function deleteAllScreenFrames(
  conversationId: string,
): Promise<ConversationScreenFrameSet> {
  const result = await fetchWithAuth<ConversationScreenFrameSet>(
    `/v1/conversations/${conversationId}/screenshots`,
    { method: 'DELETE' },
  );
  invalidateCacheKey(cacheKeys.screenFrames(conversationId));
  return result;
}

/**
 * Toggle whether this conversation's approved frames are visible on its
 * public share link. Default for a new conversation is `enabled: true`.
 */
export async function patchScreenFrameSharing(
  conversationId: string,
  enabled: boolean,
): Promise<ConversationScreenFrameSet> {
  const body: ScreenFrameSharingUpdateRequest = { enabled };
  const result = await fetchWithAuth<ConversationScreenFrameSet>(
    `/v1/conversations/${conversationId}/screenshot-sharing`,
    { method: 'PATCH', body: JSON.stringify(body) },
  );
  invalidateCacheKey(cacheKeys.screenFrames(conversationId));
  return result;
}

/**
 * Merge multiple conversations into one
 * @param conversationIds - Array of conversation IDs to merge
 * @param reprocess - Whether to reprocess the merged conversation (default: true)
 * @returns Response with status and merged conversation IDs
 */
export async function mergeConversations(
  conversationIds: string[],
  reprocess: boolean = true,
): Promise<MergeConversationsResponse> {
  return fetchWithAuth<MergeConversationsResponse>('/v1/conversations/merge', {
    method: 'POST',
    body: JSON.stringify({
      conversation_ids: conversationIds,
      reprocess,
    }),
  });
}

/**
 * Finalize an in-progress conversation from a recording session.
 * This processes the transcript, generates title/summary/action items,
 * and creates audio file records from stored chunks.
 *
 * @returns The processed conversation, or null if no in-progress conversation exists
 */
export async function processInProgressConversation(): Promise<CreateConversationResponse | null> {
  try {
    const result = await fetchWithAuth<CreateConversationResponse>('/v1/conversations', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    invalidateCache(invalidationPatterns.conversations);
    return result;
  } catch (error) {
    // 404 means no in-progress conversation exists
    if (error instanceof Error && error.message.includes('404')) {
      return null;
    }
    throw error;
  }
}

/**
 * Finalize exactly one conversation by ID (desktop-style).
 * Prefer this over processInProgressConversation when a socket owns a
 * conversation_id — the Redis in_progress pointer is shared across device +
 * web and must not steal a pendant session (#5388).
 */
export async function finalizeConversationById(
  conversationId: string,
): Promise<CreateConversationResponse | null> {
  try {
    const result = await fetchWithAuth<CreateConversationResponse>(
      `/v1/conversations/${encodeURIComponent(conversationId)}/finalize`,
      {
        method: 'POST',
        body: JSON.stringify({}),
      },
    );
    invalidateCache(invalidationPatterns.conversations);
    return result;
  } catch (error) {
    if (error instanceof Error && error.message.includes('404')) {
      return null;
    }
    throw error;
  }
}

// ============================================================================
// Action Items (Tasks) API
// ============================================================================

/**
 * Get all action items
 */
export interface GetActionItemsParams {
  limit?: number;
  offset?: number;
  completed?: boolean;
}

export async function getActionItems(
  params: GetActionItemsParams = {},
): Promise<{ items: ActionItem[]; hasMore: boolean }> {
  const { limit = 100, offset = 0, completed } = params;

  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  if (completed !== undefined) {
    queryParams.set('completed', completed.toString());
  }

  const response = await fetchWithAuth<ActionItemsResponse>(
    `/v1/action-items?${queryParams}`,
  );

  return {
    items: response.action_items || [],
    hasMore: response.has_more || false,
  };
}

/**
 * Create a new action item
 */
export interface CreateActionItemParams {
  description: string;
  due_at?: string | null;
}

export async function createActionItem(
  params: CreateActionItemParams,
): Promise<ActionItem> {
  return fetchWithAuth<ActionItem>('/v1/action-items', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/**
 * Toggle action item completion status
 */
export async function toggleActionItemCompleted(
  id: string,
  completed: boolean,
): Promise<void> {
  await fetchWithAuth(`/v1/action-items/${id}/completed?completed=${completed}`, {
    method: 'PATCH',
  });
}

/**
 * Update action item due date (for snooze functionality)
 */
export async function updateActionItemDueDate(
  id: string,
  due_at: string | null,
): Promise<void> {
  await fetchWithAuth(`/v1/action-items/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ due_at }),
  });
}

/**
 * Update action item description
 */
export async function updateActionItemDescription(
  id: string,
  description: string,
): Promise<void> {
  await fetchWithAuth(`/v1/action-items/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ description }),
  });
}

/**
 * Delete an action item
 */
export async function deleteActionItem(id: string): Promise<void> {
  await fetchWithAuth(`/v1/action-items/${id}`, {
    method: 'DELETE',
  });
  invalidateCache(invalidationPatterns.actionItems);
}

// ============================================================================
// Memories API
// ============================================================================

/**
 * Get memories list with optional filters
 */
export interface GetMemoriesParams {
  limit?: number;
  offset?: number;
  categories?: MemoryCategory[];
}

/**
 * Read memories.
 *
 * Category selection is deliberately not a parameter: `/v3/memories` accepts
 * limit, offset, cursor, and device scope only. Sending `categories` looked
 * like a filter but FastAPI drops the unknown query param, so the server
 * returned everything. Categories are applied client-side — see
 * `@/lib/memoryCategory`, which mirrors how the desktop clients do it.
 */
export async function getMemories(params: GetMemoriesParams = {}): Promise<Memory[]> {
  const { limit = 100, offset = 0 } = params;

  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  const raw = await fetchWithAuth<unknown>(`/v3/memories?${queryParams}`);
  return normalizeKnowledgeLedgerMemories(raw);
}

/**
 * Create a new memory
 */
export interface CreateMemoryParams {
  content: string;
  visibility?: MemoryVisibility;
  category?: MemoryCategory;
}

export async function createMemory(params: CreateMemoryParams): Promise<Memory> {
  const raw = await fetchWithAuth<unknown>('/v3/memories', {
    method: 'POST',
    body: JSON.stringify({
      content: params.content,
      visibility: params.visibility || 'public',
      category: params.category || 'manual',
    }),
  });
  const memory = normalizeKnowledgeLedgerMemory(raw);
  if (!memory) throw new Error('Malformed memory response');
  invalidateCache(invalidationPatterns.memories);
  return memory;
}

/**
 * Update memory content
 */
export async function updateMemoryContent(id: string, content: string): Promise<void> {
  const encodedValue = encodeURIComponent(content);
  await fetchWithAuth(`/v3/memories/${id}?value=${encodedValue}`, {
    method: 'PATCH',
  });
  invalidateCache(invalidationPatterns.memories);
}

/**
 * Update memory visibility
 */
export async function updateMemoryVisibility(
  id: string,
  visibility: MemoryVisibility,
): Promise<void> {
  await fetchWithAuth(`/v3/memories/${id}/visibility?value=${visibility}`, {
    method: 'PATCH',
  });
  invalidateCache(invalidationPatterns.memories);
}

/**
 * Delete a memory
 */
export async function deleteMemory(id: string): Promise<void> {
  await fetchWithAuth(`/v3/memories/${id}`, {
    method: 'DELETE',
  });
  invalidateCache(invalidationPatterns.memories);
}

/**
 * Delete multiple memories in a single batch request (up to 100 per call).
 * Replaces N concurrent DELETE /v3/memories/{id} calls that triggered 429 rate limits.
 */
export async function deleteMemoriesBatch(ids: string[]): Promise<void> {
  await fetchWithAuth(`/v3/memories/batch`, {
    method: 'DELETE',
    body: JSON.stringify({ memory_ids: ids }),
  });
  invalidateCache(invalidationPatterns.memories);
}

/**
 * Review a memory (accept or reject)
 */
export async function reviewMemory(id: string, accept: boolean): Promise<void> {
  await fetchWithAuth(`/v3/memories/${id}/review?value=${accept}`, {
    method: 'POST',
  });
}

// ============================================================================
// Knowledge Graph API
// ============================================================================

/**
 * Get knowledge graph data
 */
export async function getKnowledgeGraph(): Promise<KnowledgeGraph> {
  return fetchWithAuth<KnowledgeGraph>('/v1/knowledge-graph');
}

// ============================================================================
// Chat sessions API
// ============================================================================

interface ChatSessionWire {
  id: string;
  title?: string | null;
  preview?: string | null;
  created_at: string;
  updated_at: string;
  app_id?: string | null;
  message_count?: number | null;
  starred?: boolean | null;
}

function toChatSession(wire: ChatSessionWire): ChatSession {
  return {
    id: wire.id,
    title: wire.title ?? undefined,
    preview: wire.preview ?? undefined,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
    appId: wire.app_id ?? undefined,
    messageCount: wire.message_count ?? 0,
    starred: Boolean(wire.starred),
  };
}

export async function getChatSessions(appId?: string): Promise<ChatSession[]> {
  const query = appId ? `?app_id=${encodeURIComponent(appId)}` : '';
  const sessions = await fetchWithAuth<ChatSessionWire[]>(`/v2/chat-sessions${query}`);
  return Array.isArray(sessions) ? sessions.map(toChatSession) : [];
}

export async function createChatSession(
  params: { title?: string; app_id?: string } = {},
): Promise<ChatSession> {
  return toChatSession(
    await fetchWithAuth<ChatSessionWire>('/v2/chat-sessions', {
      method: 'POST',
      body: JSON.stringify(params),
    }),
  );
}

export async function updateChatSession(
  id: string,
  updates: { title?: string; starred?: boolean },
): Promise<ChatSession> {
  return toChatSession(
    await fetchWithAuth<ChatSessionWire>(`/v2/chat-sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    }),
  );
}

export async function deleteChatSession(id: string): Promise<void> {
  await fetchWithAuth(`/v2/chat-sessions/${id}`, { method: 'DELETE' });
}

export interface RealtimeSessionToken {
  provider: 'gemini';
  token: string;
  expires_at?: string;
}

export interface RealtimeUsageReport {
  input_text_tokens: number;
  input_audio_tokens: number;
  input_cached_tokens: number;
  output_text_tokens: number;
  output_audio_tokens: number;
}

interface SavedRealtimeMessage {
  id: string;
  created_at: string;
  session_id?: string | null;
}

export async function createGeminiLiveSession(): Promise<RealtimeSessionToken> {
  return fetchWithAuth<RealtimeSessionToken>('/v2/realtime/session', {
    method: 'POST',
    body: JSON.stringify({ provider: 'gemini' }),
  });
}

export async function saveRealtimeMessage(params: {
  text: string;
  sender: 'human' | 'ai';
  clientMessageId: string;
  appId?: string;
  sessionId?: string | null;
}): Promise<SavedRealtimeMessage> {
  return fetchWithAuth<SavedRealtimeMessage>('/v2/desktop/messages', {
    method: 'POST',
    body: JSON.stringify({
      text: params.text,
      sender: params.sender,
      app_id: params.appId,
      session_id: params.sessionId,
      client_message_id: params.clientMessageId,
      message_source: 'realtime_voice',
    }),
  });
}

export async function reportGeminiLiveUsage(usage: RealtimeUsageReport): Promise<void> {
  await fetchWithAuth('/v2/realtime/usage', {
    method: 'POST',
    body: JSON.stringify({
      provider: 'gemini',
      model: 'gemini-3.1-flash-live-preview',
      ...usage,
    }),
  });
}

// ============================================================================
// Goals & Scores API
// ============================================================================

/**
 * Get all goals.
 *
 * Uses `/v1/goals/all` rather than `/v1/goals/canonical/list` so the page works
 * for every signed-in user; the canonical route is gated on task-system
 * enrollment and 403s for everyone else.
 */
export async function getGoals(includeEnded = false): Promise<Goal[]> {
  const goals = await fetchWithAuth<Goal[]>(
    `/v1/goals/all?include_ended=${includeEnded}`,
  );
  return Array.isArray(goals) ? goals : [];
}

/**
 * Create body, matching what the desktop apps send
 * (`desktop/windows/src/renderer/src/pages/Goals.tsx` saveNew): title, a
 * required positive target, and unit only when the user gave one.
 *
 * `target_value` is required — the backend 422s without it — so a title-only
 * goal defaults to 1, which completes on a single tick.
 */
export interface CreateGoalParams {
  title: string;
  target_value: number;
  unit?: string;
}

export async function createGoal(params: CreateGoalParams): Promise<Goal> {
  const goal = await fetchWithAuth<Goal>('/v1/goals', {
    method: 'POST',
    body: JSON.stringify(params),
  });
  invalidateCache(invalidationPatterns.goals);
  return goal;
}

/**
 * Update only a goal's progress value.
 *
 * The backend takes `current_value` as a query parameter on this route, not in
 * the body.
 */
export async function updateGoalProgress(
  id: string,
  currentValue: number,
): Promise<Goal> {
  const goal = await fetchWithAuth<Goal>(
    `/v1/goals/${id}/progress?current_value=${encodeURIComponent(currentValue)}`,
    { method: 'PATCH' },
  );
  invalidateCache(invalidationPatterns.goals);
  return goal;
}

export interface UpdateGoalParams {
  title?: string;
  target_value?: number;
  current_value?: number;
  unit?: string | null;
}

export async function updateGoal(id: string, updates: UpdateGoalParams): Promise<Goal> {
  const goal = await fetchWithAuth<Goal>(`/v1/goals/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
  invalidateCache(invalidationPatterns.goals);
  return goal;
}

export async function deleteGoal(id: string): Promise<void> {
  await fetchWithAuth(`/v1/goals/${id}`, { method: 'DELETE' });
  invalidateCache(invalidationPatterns.goals);
}

/**
 * Recorded progress values for a goal, newest window first.
 *
 * Uses `/v1/goals/{id}/history`, not `/v1/goals/{id}/detail`. The detail
 * projection and the progress-events feed both sit behind
 * `require_canonical_task_user`, which 404s for anyone not enrolled in the
 * canonical task system — most web users.
 */
export async function getGoalHistory(id: string, days = 30): Promise<GoalHistoryEntry[]> {
  const history = await fetchWithAuth<GoalHistoryEntry[]>(
    `/v1/goals/${id}/history?days=${days}`,
  );
  return Array.isArray(history) ? history : [];
}

/** AI-generated advice for a goal. Rate limited server-side. */
export async function getGoalAdvice(id: string): Promise<string> {
  const response = await fetchWithAuth<{ advice: string }>(`/v1/goals/${id}/advice`);
  return response.advice;
}

// ============================================================================

/** Daily, weekly, and overall task-completion scores. */
export async function getScores(date?: string): Promise<Scores> {
  const query = date ? `?date=${encodeURIComponent(date)}` : '';
  return fetchWithAuth<Scores>(`/v1/scores${query}`);
}

// ============================================================================
// Chat/Messages API
// ============================================================================

/**
 * Decode base64 string to UTF-8 text
 * Handles multi-byte UTF-8 characters correctly
 */
function decodeBase64Utf8(base64: string): string {
  try {
    // Decode base64 to binary string
    const binaryString = atob(base64);
    // Convert binary string to Uint8Array
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    // Decode as UTF-8
    const decoder = new TextDecoder('utf-8');
    return decoder.decode(bytes);
  } catch (e) {
    console.error('Failed to decode base64 UTF-8:', e);
    // Fallback to simple atob
    return atob(base64);
  }
}

/**
 * Parse a streaming response line into a MessageChunk
 */
export function parseStreamLine(line: string): MessageChunk | null {
  if (!line || line.trim() === '') return null;

  if (line.startsWith('think: ')) {
    return {
      type: 'think' as MessageChunkType,
      text: line.slice(7).replace(/__CRLF__/g, '\n'),
    };
  }
  if (line.startsWith('data: ')) {
    return {
      type: 'data' as MessageChunkType,
      text: line.slice(6).replace(/__CRLF__/g, '\n'),
    };
  }
  if (line.startsWith('done: ')) {
    try {
      const decoded = decodeBase64Utf8(line.slice(6));
      const message = JSON.parse(decoded) as ServerMessage;
      return {
        type: 'done' as MessageChunkType,
        text: decoded,
        message,
      };
    } catch (e) {
      console.error('Failed to parse done chunk:', e);
      return null;
    }
  }
  if (line.startsWith('message: ')) {
    try {
      const decoded = decodeBase64Utf8(line.slice(9));
      const message = JSON.parse(decoded) as ServerMessage;
      return {
        type: 'message' as MessageChunkType,
        text: decoded,
        message,
      };
    } catch (e) {
      console.error('Failed to parse message chunk:', e);
      return null;
    }
  }
  if (line.startsWith('error: ')) {
    return {
      type: 'error' as MessageChunkType,
      text: line.slice(7),
    };
  }

  return null;
}

/**
 * Get message history
 */
export async function getMessages(
  appId?: string,
  chatSessionId?: string | null,
): Promise<ServerMessage[]> {
  const queryParams = new URLSearchParams();
  if (appId) {
    queryParams.set('app_id', appId);
  }
  // Omitted entirely for the default shared thread; naming a session targets
  // that one specific thread.
  if (chatSessionId) {
    queryParams.set('chat_session_id', chatSessionId);
  }

  const endpoint = `/v2/messages${queryParams.toString() ? `?${queryParams}` : ''}`;
  return fetchWithAuth<ServerMessage[]>(endpoint);
}

/**
 * Send a message with streaming response
 */
export async function sendMessageStream(
  text: string,
  onChunk: (chunk: MessageChunk) => void,
  options?: {
    appId?: string;
    /** Target one specific thread; omit for the default shared thread. */
    chatSessionId?: string | null;
    fileIds?: string[];
    context?: {
      type: string;
      id?: string;
      title?: string;
      summary?: string;
      start_date?: string;
      end_date?: string;
    } | null;
  },
): Promise<void> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const queryParams = new URLSearchParams();
  if (options?.appId) {
    queryParams.set('app_id', options.appId);
  }
  // Without this the reply is persisted to the default shared thread while the
  // UI shows it under the selected one.
  if (options?.chatSessionId) {
    queryParams.set('chat_session_id', options.chatSessionId);
  }

  const url = `${API_BASE_URL}/v2/messages${queryParams.toString() ? `?${queryParams}` : ''}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'X-App-Platform': 'web',
    },
    body: JSON.stringify({
      text,
      file_ids: options?.fileIds || [],
      context: options?.context
        ? {
            type: options.context.type === 'general' ? 'recap' : options.context.type,
            id: options.context.id,
            title: options.context.title,
            start_date: options.context.start_date,
            end_date: options.context.end_date,
          }
        : null,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Send message error:', response.status, errorText);
    throw new Error(`Failed to send message: ${response.status}`);
  }

  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete lines
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep incomplete line in buffer

      for (const line of lines) {
        const chunk = parseStreamLine(line);
        if (chunk) {
          onChunk(chunk);
        }
      }
    }

    // Process any remaining buffer
    if (buffer) {
      const chunk = parseStreamLine(buffer);
      if (chunk) {
        onChunk(chunk);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Clear message history
 */
export async function clearMessages(
  appId?: string,
  chatSessionId?: string | null,
): Promise<void> {
  const queryParams = new URLSearchParams();
  if (appId) {
    queryParams.set('app_id', appId);
  }
  // Clearing must delete the thread the reader is looking at, not the shared one.
  if (chatSessionId) {
    queryParams.set('chat_session_id', chatSessionId);
  }

  const endpoint = `/v2/messages${queryParams.toString() ? `?${queryParams}` : ''}`;
  await fetchWithAuth(endpoint, {
    method: 'DELETE',
  });
}

/**
 * Upload files for chat
 */
export async function uploadChatFiles(
  files: File[],
  appId?: string,
): Promise<MessageFile[]> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const queryParams = new URLSearchParams();
  if (appId) {
    queryParams.set('app_id', appId);
  }

  const url = `${API_BASE_URL}/v2/files${queryParams.toString() ? `?${queryParams}` : ''}`;

  const formData = new FormData();
  for (const file of files) {
    // Append with explicit filename to ensure proper handling
    formData.append('files', file, file.name);
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Upload files error:', response.status, errorText);
    throw new Error(`Failed to upload files: ${response.status}`);
  }

  return response.json();
}

/**
 * Transcribe voice message to text
 */
function getAudioFileExtension(mimeType: string): string {
  const normalizedMimeType = mimeType.split(';', 1)[0].toLowerCase();
  if (normalizedMimeType === 'audio/webm' || normalizedMimeType === 'video/webm')
    return 'webm';
  if (normalizedMimeType === 'audio/mp4' || normalizedMimeType === 'video/mp4')
    return 'mp4';
  return 'wav';
}

export async function transcribeVoiceMessage(audioBlob: Blob): Promise<string> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const url = `${API_BASE_URL}/v2/voice-message/transcribe`;

  const formData = new FormData();
  // The backend uses the filename extension when it uploads audio for STT.
  formData.append('files', audioBlob, `audio.${getAudioFileExtension(audioBlob.type)}`);
  const deviceIdHash = await getWebDeviceIdHash();
  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
    'X-App-Platform': 'web',
  };
  if (deviceIdHash) {
    headers['X-Device-Id-Hash'] = deviceIdHash;
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Transcribe error:', response.status, errorText);
    throw new Error(`Failed to transcribe audio: ${response.status}`);
  }

  const data = await response.json();
  return data.transcript || '';
}

// ============================================================================
// Apps API
// ============================================================================

// Re-export App type for backward compatibility
export type { App } from '@/types/apps';

/**
 * Get apps grouped by capability (for explore page)
 */
export async function getAppsGrouped(
  params: {
    capability?: string;
    offset?: number;
    limit?: number;
  } = {},
): Promise<AppsGroupedResponse> {
  const { capability, offset = 0, limit = 20 } = params;

  const queryParams = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
  });

  if (capability) {
    queryParams.set('capability', capability);
  }

  return fetchWithAuth<AppsGroupedResponse>(`/v2/apps?${queryParams}`);
}

/**
 * Search apps with filters
 */
export async function searchApps(
  params: AppsSearchParams = {},
): Promise<AppsSearchResponse> {
  const queryParams = new URLSearchParams();

  if (params.q) queryParams.set('q', params.q);
  if (params.category) queryParams.set('category', params.category);
  if (params.capability) queryParams.set('capability', params.capability);
  if (params.rating !== undefined) queryParams.set('rating', params.rating.toString());
  if (params.sort) queryParams.set('sort', params.sort);
  if (params.my_apps) queryParams.set('my_apps', 'true');
  if (params.installed_apps) queryParams.set('installed_apps', 'true');
  queryParams.set('offset', (params.offset || 0).toString());
  queryParams.set('limit', (params.limit || 20).toString());

  return fetchWithAuth<AppsSearchResponse>(`/v2/apps/search?${queryParams}`);
}

/**
 * Get popular apps
 */
export async function getPopularApps(): Promise<App[]> {
  return fetchWithAuth<App[]>('/v1/apps/popular');
}

/**
 * Get a single app by ID
 */
export async function getApp(appId: string): Promise<App> {
  return fetchWithAuth<App>(`/v1/apps/${appId}`);
}

/**
 * Get app categories
 */
export async function getAppCategories(): Promise<AppCategory[]> {
  return fetchWithAuth<AppCategory[]>('/v1/app-categories');
}

/**
 * Get app capabilities
 */
export async function getAppCapabilities(): Promise<AppCapability[]> {
  return fetchWithAuth<AppCapability[]>('/v1/app-capabilities');
}

/**
 * Enable (install) an app
 */
export async function enableApp(appId: string): Promise<{ status: string }> {
  return fetchWithAuth<{ status: string }>(`/v1/apps/enable?app_id=${appId}`, {
    method: 'POST',
  });
}

/**
 * Disable (uninstall) an app
 */
export async function disableApp(appId: string): Promise<{ status: string }> {
  return fetchWithAuth<{ status: string }>(`/v1/apps/disable?app_id=${appId}`, {
    method: 'POST',
  });
}

/**
 * Get installed apps
 */
export async function getInstalledApps(): Promise<AppsSearchResponse> {
  return searchApps({ installed_apps: true, limit: 100 });
}

/**
 * Get chat-enabled apps (apps with 'chat' or 'persona' capability)
 */
export async function getChatApps(): Promise<App[]> {
  const response = await searchApps({ installed_apps: true, limit: 100 });
  return response.data.filter(
    (app) => app.capabilities?.includes('chat') || app.capabilities?.includes('persona'),
  );
}

// ============================================================================
// App Creation/Editing API
// ============================================================================

/**
 * Create a new app
 */
export async function createApp(
  data: CreateAppRequest & {
    deleted?: boolean;
    price?: number;
    thumbnails?: string[];
    uid?: string;
  },
  imageFile?: File,
): Promise<{ app_id: string }> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const url = `${API_BASE_URL}/v1/apps`;

  const formData = new FormData();
  formData.append('app_data', JSON.stringify(data));
  if (imageFile) {
    formData.append('file', imageFile, imageFile.name);
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Create app error:', response.status, errorText);
    throw new Error(`Failed to create app: ${response.status}`);
  }

  return response.json();
}

/**
 * Update an existing app
 */
export async function updateApp(
  appId: string,
  data: Partial<CreateAppRequest>,
  imageFile?: File,
): Promise<void> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const url = `${API_BASE_URL}/v1/apps/${appId}`;

  // The API requires the id to be included in the app_data
  const dataWithId = { ...data, id: appId };

  const formData = new FormData();
  formData.append('app_data', JSON.stringify(dataWithId));
  if (imageFile) {
    formData.append('file', imageFile, imageFile.name);
  }

  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Update app error:', response.status, errorText);
    throw new Error(`Failed to update app: ${response.status}`);
  }
}

/**
 * Re-enable an app that the backend auto-disabled after webhook failures.
 *
 * Sends `disabled: false` explicitly — the backend re-enable branch reads an
 * unset-exclusive payload, so omitting the field is a no-op rather than a
 * failure. The endpoint re-checks every configured URL and rejects the request
 * with a specific reason, so that detail is surfaced instead of the status code.
 */
export async function reEnableApp(appId: string): Promise<void> {
  const token = await getIdToken();
  if (!token) {
    throw new Error('Not authenticated');
  }

  const formData = new FormData();
  formData.append('app_data', JSON.stringify({ id: appId, disabled: false }));

  const response = await fetch(`${API_BASE_URL}/v1/apps/${appId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body?.detail)
      .catch(() => null);
    throw new Error(detail || `Failed to re-enable app: ${response.status}`);
  }
}

/**
 * Delete an app
 */
export async function deleteApp(appId: string): Promise<void> {
  await fetchWithAuth(`/v1/apps/${appId}`, {
    method: 'DELETE',
  });
}

/**
 * Upload app thumbnail
 */
export async function uploadAppThumbnail(file: File): Promise<ThumbnailUploadResponse> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const url = `${API_BASE_URL}/v1/app/thumbnails`;

  const formData = new FormData();
  formData.append('file', file, file.name);

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Upload thumbnail error:', response.status, errorText);
    throw new Error(`Failed to upload thumbnail: ${response.status}`);
  }

  return response.json();
}

/**
 * Generate app description using AI
 */
export async function generateAppDescription(
  name: string,
  currentDescription: string,
): Promise<string> {
  const response = await fetchWithAuth<GenerateDescriptionResponse>(
    '/v1/app/generate-description',
    {
      method: 'POST',
      body: JSON.stringify({ name, description: currentDescription }),
    },
  );
  return response.description;
}

/**
 * Generate app description and emoji using AI
 * Used for quick template creation (matches mobile app behavior)
 */
export async function generateAppDescriptionAndEmoji(
  name: string,
  prompt: string,
): Promise<{ description: string; emoji: string }> {
  try {
    const response = await fetchWithAuth<{
      description: string;
      emoji: string;
    }>('/v1/app/generate-description-emoji', {
      method: 'POST',
      body: JSON.stringify({ name, prompt }),
    });
    return {
      description: response.description || '',
      emoji: response.emoji || '✨',
    };
  } catch {
    // Fallback: generate description only and use default emoji
    const description = await generateAppDescription(name, prompt);
    return { description, emoji: '✨' };
  }
}

/**
 * Get proactive notification scopes
 * Note: This endpoint may not exist in all API versions, returns empty array on 404
 */
export async function getNotificationScopes(): Promise<NotificationScope[]> {
  try {
    const token = await getIdToken();
    if (!token) return [];

    const response = await fetch(
      `${API_BASE_URL}/v1/apps/proactive-notification-scopes`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-App-Platform': 'web',
        },
      },
    );

    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

/**
 * Get available payment plans
 * Note: This endpoint may not exist in all API versions, returns empty array on 404
 */
export async function getPaymentPlans(): Promise<PaymentPlan[]> {
  try {
    const token = await getIdToken();
    if (!token) return [];

    const response = await fetch(`${API_BASE_URL}/v1/app/plans`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-App-Platform': 'web',
      },
    });

    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

// ============================================================================
// User Settings API
// ============================================================================

import type {
  DailySummarySettings,
  TranscriptionPreferences,
  DeveloperWebhooks,
  WebhookSettings,
  RecordingPermission,
  UserUsage,
  UserUsageResponse,
  UsageStats,
  AllUsageData,
  UserSubscription,
  UserSubscriptionResponse,
  Person,
} from '@/types/user';
import { decodePlan, planGrantsPaidCapability } from '@/types/user';

/**
 * Get user's primary language
 */
export async function getUserLanguage(): Promise<string> {
  const response = await fetchWithAuth<{ language: string }>('/v1/users/language');
  return response.language;
}

/**
 * Set user's primary language
 */
export async function setUserLanguage(language: string): Promise<void> {
  await fetchWithAuth('/v1/users/language', {
    method: 'PATCH',
    body: JSON.stringify({ language }),
  });
}

/**
 * Get daily summary settings
 */
export async function getDailySummarySettings(): Promise<DailySummarySettings> {
  return fetchWithAuth<DailySummarySettings>('/v1/users/daily-summary-settings');
}

/**
 * Update daily summary settings
 */
export async function updateDailySummarySettings(
  settings: DailySummarySettings,
): Promise<void> {
  await fetchWithAuth('/v1/users/daily-summary-settings', {
    method: 'PATCH',
    body: JSON.stringify(settings),
  });
}

// ============================================================================
// Daily Summaries (Recaps) API
// ============================================================================

import type { DailySummary } from '@/types/recap';

export interface GetDailySummariesParams {
  limit?: number;
  offset?: number;
}

/**
 * Get list of daily summaries with pagination
 */
export async function getDailySummaries(
  params: GetDailySummariesParams = {},
): Promise<DailySummary[]> {
  const { limit = 30, offset = 0 } = params;
  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  return fetchWithAuth<DailySummary[]>(`/v1/users/daily-summaries?${queryParams}`);
}

/**
 * Get a single daily summary by ID
 */
export async function getDailySummary(id: string): Promise<DailySummary> {
  return fetchWithAuth<DailySummary>(`/v1/users/daily-summaries/${id}`);
}

/**
 * Delete a daily summary
 */
export async function deleteDailySummary(id: string): Promise<void> {
  await fetchWithAuth(`/v1/users/daily-summaries/${id}`, {
    method: 'DELETE',
  });
}

/**
 * Generate a test daily summary for a specific date
 */
export async function generateTestDailySummary(date: string): Promise<DailySummary> {
  return fetchWithAuth<DailySummary>('/v1/users/daily-summary-settings/test', {
    method: 'POST',
    body: JSON.stringify({ date }),
  });
}

/**
 * Get transcription preferences
 */
export async function getTranscriptionPreferences(): Promise<TranscriptionPreferences> {
  return fetchWithAuth<TranscriptionPreferences>('/v1/users/transcription-preferences');
}

// Webhook type enum matching backend API
type WebhookType =
  'memory_created' | 'realtime_transcript' | 'audio_bytes' | 'day_summary';

/**
 * Get developer webhook URL
 */
export async function getDeveloperWebhook(type: WebhookType): Promise<WebhookSettings> {
  return fetchWithAuth<WebhookSettings>(`/v1/users/developer/webhook/${type}`);
}

/**
 * Set developer webhook URL
 */
export async function setDeveloperWebhook(type: WebhookType, url: string): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/**
 * Enable developer webhook
 */
export async function enableDeveloperWebhook(type: WebhookType): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}/enable`, {
    method: 'POST',
  });
}

/**
 * Disable developer webhook
 */
export async function disableDeveloperWebhook(type: WebhookType): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}/disable`, {
    method: 'POST',
  });
}

/**
 * Get all webhook statuses
 */
export async function getDeveloperWebhooksStatus(): Promise<DeveloperWebhooks> {
  return fetchWithAuth<DeveloperWebhooks>('/v1/users/developer/webhooks/status');
}

/**
 * Get store recording permission
 */
export async function getRecordingPermission(): Promise<RecordingPermission> {
  return fetchWithAuth<RecordingPermission>('/v1/users/store-recording-permission');
}

/**
 * Set store recording permission
 */
export async function setRecordingPermission(enabled: boolean): Promise<void> {
  await fetchWithAuth(`/v1/users/store-recording-permission?value=${enabled}`, {
    method: 'POST',
  });
}

/**
 * Get user usage stats for a specific period
 */
export async function getUserUsage(
  period: 'today' | 'monthly' | 'yearly' | 'all_time' = 'monthly',
): Promise<UserUsage | null> {
  try {
    const response = await fetchWithAuth<UserUsageResponse>(
      `/v1/users/me/usage?period=${period}`,
    );

    // Extract the relevant period's stats
    let stats: UsageStats | undefined;
    if (period === 'all_time') {
      stats = response.all_time;
    } else if (period === 'yearly') {
      stats = response.yearly;
    } else if (period === 'monthly') {
      stats = response.monthly;
    } else if (period === 'today') {
      stats = response.today;
    }

    // Fallback to any available stats
    if (!stats) {
      stats = response.all_time || response.monthly || response.yearly || response.today;
    }

    // Return data if we have stats OR history - some periods might have history without aggregate stats
    if (stats || response.history?.length) {
      return {
        transcription_seconds: stats?.transcription_seconds || 0,
        words_transcribed: stats?.words_transcribed || 0,
        insights_gained: stats?.insights_gained || 0,
        memories_created: stats?.memories_created || 0,
        history: response.history,
      };
    }
    return null;
  } catch (error) {
    console.error('getUserUsage error:', error);
    return null;
  }
}

/**
 * Get all usage data for all periods (for tabs display)
 */
export async function getAllUsageData(): Promise<AllUsageData> {
  const [today, monthly, yearly, all_time] = await Promise.all([
    getUserUsage('today'),
    getUserUsage('monthly'),
    getUserUsage('yearly'),
    getUserUsage('all_time'),
  ]);
  return { today, monthly, yearly, all_time };
}

/**
 * Get user subscription info
 */
export async function getUserSubscription(): Promise<UserSubscription | null> {
  try {
    const response = await fetchWithAuth<UserSubscriptionResponse>(
      '/v1/users/me/subscription',
    );

    const plan = decodePlan(response.subscription?.plan);
    const result: UserSubscription = {
      plan: plan.raw ?? '',
      plan_identity: plan,
      status: response.subscription?.status || 'active',
      // Unknown plans are deliberately excluded. A future wire value must not
      // inherit paid capability merely because it is non-empty.
      is_unlimited: planGrantsPaidCapability(plan),
      current_period_end: response.subscription?.current_period_end,
      stripe_subscription_id: response.subscription?.stripe_subscription_id,
      cancel_at_period_end: response.subscription?.cancel_at_period_end,
      current_price_id: response.subscription?.current_price_id,
      features: response.subscription?.features || [],
    };
    return result;
  } catch (error) {
    console.error('getUserSubscription error:', error);
    return null;
  }
}

/**
 * Get available subscription plans
 */
export async function getAvailablePlans(): Promise<AvailablePlansResponse | null> {
  try {
    const response = await fetchWithAuth<AvailablePlansResponse>(
      '/v1/payments/available-plans',
    );
    return response;
  } catch (error) {
    console.error('getAvailablePlans error:', error);
    return null;
  }
}

/**
 * Create a checkout session for subscription
 */
export async function createCheckoutSession(
  priceId: string,
): Promise<CheckoutSessionResponse | null> {
  try {
    const response = await fetchWithAuth<CheckoutSessionResponse>(
      '/v1/payments/checkout-session',
      {
        method: 'POST',
        body: JSON.stringify({ price_id: priceId }),
      },
    );
    return response;
  } catch (error) {
    console.error('createCheckoutSession error:', error);
    return null;
  }
}

/**
 * Upgrade subscription to a different plan
 */
export async function upgradeSubscription(
  priceId: string,
): Promise<UpgradeSubscriptionResponse | null> {
  try {
    const response = await fetchWithAuth<UpgradeSubscriptionResponse>(
      '/v1/payments/upgrade-subscription',
      {
        method: 'POST',
        body: JSON.stringify({ price_id: priceId }),
      },
    );
    return response;
  } catch (error) {
    console.error('upgradeSubscription error:', error);
    return null;
  }
}

/**
 * Cancel subscription
 */
export async function cancelSubscription(): Promise<CancelSubscriptionResponse | null> {
  try {
    const response = await fetchWithAuth<CancelSubscriptionResponse>(
      '/v1/payments/subscription',
      {
        method: 'DELETE',
      },
    );
    return response;
  } catch (error) {
    console.error('cancelSubscription error:', error);
    return null;
  }
}

/**
 * Get customer portal URL for managing payment methods
 */
export async function getCustomerPortal(): Promise<CustomerPortalResponse | null> {
  try {
    const response = await fetchWithAuth<CustomerPortalResponse>(
      '/v1/payments/customer-portal',
      {
        method: 'POST',
      },
    );
    return response;
  } catch (error) {
    console.error('getCustomerPortal error:', error);
    return null;
  }
}

/**
 * Get all people for speaker identification
 */
export async function getPeople(): Promise<Person[]> {
  return fetchWithAuth<Person[]>('/v1/users/people');
}

/**
 * Create a new person
 */
export async function createPerson(name: string): Promise<Person> {
  return fetchWithAuth<Person>('/v1/users/people', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

/**
 * Update person name
 */
export async function updatePersonName(personId: string, name: string): Promise<void> {
  await fetchWithAuth(`/v1/users/people/${personId}/name`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

/**
 * Delete a person
 */
export async function deletePerson(personId: string): Promise<void> {
  await fetchWithAuth(`/v1/users/people/${personId}`, {
    method: 'DELETE',
  });
}

/**
 * Bulk assign speaker to transcript segments
 * @param conversationId - The conversation ID
 * @param segmentIds - Array of segment IDs to assign
 * @param isUser - If true, marks segments as user's speech
 * @param personId - Person ID to assign (null to unassign)
 */
export async function assignBulkTranscriptSegments(
  conversationId: string,
  segmentIds: string[],
  options: { isUser?: boolean; personId?: string | null },
): Promise<void> {
  const { isUser, personId } = options;

  let assignType: 'is_user' | 'person_id';
  let value: string | null;

  if (isUser) {
    assignType = 'is_user';
    value = 'true';
  } else {
    assignType = 'person_id';
    value = personId ?? null;
  }

  await fetchWithAuth(`/v1/conversations/${conversationId}/segments/assign-bulk`, {
    method: 'PATCH',
    body: JSON.stringify({
      segment_ids: segmentIds,
      assign_type: assignType,
      value,
    }),
  });
}

/**
 * Error thrown when editing a transcript segment requires a paid plan
 * (backend returns HTTP 402 for `/segments/text` on gated accounts).
 */
export class SegmentEditPlanRequiredError extends Error {
  constructor(message = 'Editing the transcript requires the Unlimited plan.') {
    super(message);
    this.name = 'SegmentEditPlanRequiredError';
  }
}

/**
 * Update the text of a single transcript segment.
 *
 * Mirrors the backend `PATCH /v1/conversations/{id}/segments/text`
 * (`UpdateSegmentTextRequest`), which identifies the segment by its `id` and
 * rewrites just that segment's text. The response is a bare `{status}`, so
 * callers must optimistically patch their local `transcript_segments`.
 *
 * @param conversationId - The conversation ID
 * @param segmentId - The `id` of the segment to edit (non-empty)
 * @param text - New segment text (1–10000 chars, enforced by the backend)
 * @throws SegmentEditPlanRequiredError when the account is plan-gated (402)
 */
export async function updateSegmentText(
  conversationId: string,
  segmentId: string,
  text: string,
): Promise<void> {
  try {
    await fetchWithAuth(`/v1/conversations/${conversationId}/segments/text`, {
      method: 'PATCH',
      body: JSON.stringify({ segment_id: segmentId, text }),
    });
  } catch (error) {
    // fetchWithAuth surfaces the status in the thrown message (`API error: 402 ...`).
    if (error instanceof Error && error.message.includes('402')) {
      throw new SegmentEditPlanRequiredError();
    }
    throw error;
  }
}

/**
 * Delete account permanently
 */
export async function deleteAccount(): Promise<void> {
  await fetchWithAuth('/v1/users/delete-account', {
    method: 'DELETE',
  });
}

/**
 * Get training data opt-in status
 */
export async function getTrainingDataOptIn(): Promise<{ opted_in: boolean }> {
  return fetchWithAuth<{ opted_in: boolean }>('/v1/users/training-data-opt-in');
}

/**
 * Set training data opt-in
 */
export async function setTrainingDataOptIn(optIn: boolean): Promise<void> {
  await fetchWithAuth('/v1/users/training-data-opt-in', {
    method: 'POST',
    body: JSON.stringify({ opted_in: optIn }),
  });
}

// ============================================================================
// Developer API Keys
// ============================================================================

import type {
  DeveloperApiKey,
  CustomVocabulary,
  Integration,
  McpApiKey,
  AvailablePlansResponse,
  CheckoutSessionResponse,
  UpgradeSubscriptionResponse,
  CancelSubscriptionResponse,
  CustomerPortalResponse,
} from '@/types/user';

/**
 * Get user's developer API keys
 */
export async function getDeveloperApiKeys(): Promise<DeveloperApiKey[]> {
  try {
    return await fetchWithAuth<DeveloperApiKey[]>('/v1/dev/keys');
  } catch {
    return [];
  }
}

/**
 * Create a new developer API key with optional scopes
 */
export async function createDeveloperApiKey(
  name: string,
  scopes?: string[],
): Promise<DeveloperApiKey> {
  const body: { name: string; scopes?: string[] } = { name };
  if (scopes && scopes.length > 0) {
    body.scopes = scopes;
  }
  return fetchWithAuth<DeveloperApiKey>('/v1/dev/keys', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * Delete a developer API key
 */
export async function deleteDeveloperApiKey(keyId: string): Promise<void> {
  await fetchWithAuth(`/v1/dev/keys/${keyId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// MCP API Keys
// ============================================================================

/**
 * Get user's MCP API keys
 */
export async function getMcpApiKeys(): Promise<McpApiKey[]> {
  try {
    return await fetchWithAuth<McpApiKey[]>('/v1/mcp/keys');
  } catch {
    return [];
  }
}

/**
 * Create a new MCP API key
 */
export async function createMcpApiKey(name: string): Promise<McpApiKey> {
  return fetchWithAuth<McpApiKey>('/v1/mcp/keys', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

/**
 * Delete an MCP API key
 */
export async function deleteMcpApiKey(keyId: string): Promise<void> {
  await fetchWithAuth(`/v1/mcp/keys/${keyId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Data Export & Knowledge Graph
// ============================================================================

/**
 * Export all user data as a downloadable JSON blob (streamed from backend).
 */
export async function exportAllData(): Promise<Blob> {
  const token = await getIdToken();
  if (!token) {
    throw new Error('Not authenticated');
  }
  const response = await fetch(`${API_BASE_URL}/v1/users/export`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status} ${response.statusText}`);
  }
  return response.blob();
}

/**
 * Delete the knowledge graph
 */
export async function deleteKnowledgeGraph(): Promise<void> {
  await fetchWithAuth('/v1/knowledge-graph', {
    method: 'DELETE',
  });
}

// ============================================================================
// Custom Vocabulary (via Transcription Preferences)
// ============================================================================

/**
 * Get custom vocabulary words from transcription preferences
 */
export async function getCustomVocabulary(): Promise<string[]> {
  try {
    const result = await fetchWithAuth<TranscriptionPreferences>(
      '/v1/users/transcription-preferences',
    );
    return result.vocabulary || [];
  } catch {
    return [];
  }
}

/**
 * Update custom vocabulary words via transcription preferences
 */
export async function updateCustomVocabulary(words: string[]): Promise<void> {
  await fetchWithAuth('/v1/users/transcription-preferences', {
    method: 'PATCH',
    body: JSON.stringify({ vocabulary: words }),
  });
}

// ============================================================================
// Integrations
// ============================================================================

// Integration definitions with logo paths
const INTEGRATION_DEFINITIONS: Array<{
  id: string;
  appKey: string;
  name: string;
  description: string;
  logo: string;
  coming_soon?: boolean;
}> = [
  {
    id: 'google_calendar',
    appKey: 'google_calendar',
    name: 'Google Calendar',
    description: 'Sync with your calendar',
    logo: '/integrations/google-calendar.png',
  },
  {
    id: 'whoop',
    appKey: 'whoop',
    name: 'Whoop',
    description: 'Health & fitness tracking',
    logo: '/integrations/whoop.png',
  },
  {
    id: 'notion',
    appKey: 'notion',
    name: 'Notion',
    description: 'Sync notes to Notion',
    logo: '/integrations/notion-logo.png',
  },
  {
    id: 'github',
    appKey: 'github',
    name: 'GitHub',
    description: 'Create issues and notes',
    logo: '/integrations/github-logo.png',
  },
  {
    id: 'twitter',
    appKey: 'twitter',
    name: 'X (Twitter)',
    description: 'Share to Twitter',
    logo: '/integrations/x-logo.avif',
  },
  {
    id: 'gmail',
    appKey: 'gmail',
    name: 'Gmail',
    description: 'Email integrations',
    logo: '/integrations/gmail-logo.jpeg',
  },
];

/**
 * Get individual integration connection status (like mobile app)
 */
async function getIntegrationStatus(appKey: string): Promise<{ connected: boolean }> {
  try {
    const response = await fetchWithAuth<{
      connected: boolean;
      app_key: string;
    }>(`/v1/integrations/${appKey}`);
    return { connected: response.connected ?? false };
  } catch {
    return { connected: false };
  }
}

/**
 * Get available integrations with connection status
 * Fetches individual integration statuses like the mobile app does
 */
export async function getIntegrations(): Promise<Integration[]> {
  // Fetch all integration statuses in parallel
  const statusPromises = INTEGRATION_DEFINITIONS.map(async (def) => {
    const status = await getIntegrationStatus(def.appKey);
    return {
      id: def.id,
      name: def.name,
      description: def.description,
      icon: def.logo,
      connected: status.connected,
      coming_soon: def.coming_soon,
    };
  });

  return Promise.all(statusPromises);
}

/**
 * Get OAuth URL for an integration
 * Opens the OAuth flow for the user to authorize
 */
export async function getIntegrationOAuthUrl(
  integrationId: string,
): Promise<string | null> {
  try {
    const response = await fetchWithAuth<{ auth_url: string }>(
      `/v1/integrations/${integrationId}/oauth-url`,
    );
    return response.auth_url || null;
  } catch {
    return null;
  }
}

/**
 * Disconnect an integration
 */
export async function disconnectIntegration(integrationId: string): Promise<void> {
  await fetchWithAuth(`/v1/integrations/${integrationId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Conversation Reprocessing API
// ============================================================================

/**
 * Reprocess a conversation with an optional specific app
 * @param conversationId - The ID of the conversation to reprocess
 * @param appId - Optional app ID to use for processing (if provided, only this app will be triggered)
 * @returns The updated conversation after reprocessing
 */
export async function reprocessConversation(
  conversationId: string,
  appId?: string,
): Promise<Conversation> {
  const queryParams = new URLSearchParams();
  if (appId) {
    queryParams.set('app_id', appId);
  }

  const endpoint = `/v1/conversations/${conversationId}/reprocess${queryParams.toString() ? `?${queryParams}` : ''}`;
  return fetchWithAuth<Conversation>(endpoint, {
    method: 'POST',
  });
}

/**
 * Update a conversation's title
 * @param conversationId - The ID of the conversation
 * @param title - The new title
 */
export async function updateConversationTitle(
  conversationId: string,
  title: string,
): Promise<void> {
  await fetchWithAuth(
    `/v1/conversations/${conversationId}/title?title=${encodeURIComponent(title)}`,
    {
      method: 'PATCH',
    },
  );
}

/**
 * Test a custom prompt against a conversation
 * @param conversationId - The ID of the conversation
 * @param prompt - The custom prompt to test
 * @returns The generated summary
 */
export async function testConversationPrompt(
  conversationId: string,
  prompt: string,
): Promise<string> {
  const response = await fetchWithAuth<{ summary: string }>(
    `/v1/conversations/${conversationId}/test-prompt`,
    {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    },
  );
  return response.summary;
}

// =============================================================================
// Audio API
// =============================================================================

/**
 * Get the streaming URL for an audio file
 * @param conversationId - The conversation ID
 * @param audioFileId - The audio file ID
 * @param format - Audio format (default: wav)
 */
export function getAudioStreamUrl(
  conversationId: string,
  audioFileId: string,
  format: string = 'wav',
): string {
  return `${API_BASE_URL}/v1/sync/audio/${conversationId}/${audioFileId}?format=${format}`;
}

/**
 * Get signed URLs for conversation audio files
 * Returns direct GCS URLs for cached files or status for pending files
 * @param conversationId - The conversation ID
 */
export async function getConversationAudioUrls(
  conversationId: string,
  signal?: AbortSignal,
): Promise<AudioFileUrlInfo[]> {
  try {
    const response = await fetchWithAuth<{ audio_files: AudioFileUrlInfo[] }>(
      `/v1/sync/audio/${conversationId}/urls`,
      { signal },
    );
    return response.audio_files || [];
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return []; // Silently return empty for aborted requests
    }
    console.error('Error fetching audio URLs:', error);
    return [];
  }
}

/**
 * Get signed URLs plus the server's poll hint (poll_after_ms) while
 * playback artifacts are still being built.
 * @param conversationId - The conversation ID
 */
export async function getConversationAudioUrlsWithPoll(
  conversationId: string,
  signal?: AbortSignal,
): Promise<{ files: AudioFileUrlInfo[]; pollAfterMs: number | null }> {
  try {
    const response = await fetchWithAuth<{
      audio_files: AudioFileUrlInfo[];
      poll_after_ms?: number | null;
    }>(`/v1/sync/audio/${conversationId}/urls`, { signal });
    return {
      files: response.audio_files || [],
      pollAfterMs: response.poll_after_ms ?? null,
    };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return { files: [], pollAfterMs: null };
    }
    console.error('Error fetching audio URLs:', error);
    return { files: [], pollAfterMs: null };
  }
}

/**
 * Pre-cache audio files for a conversation
 * Triggers background caching of audio files for faster playback
 * @param conversationId - The conversation ID
 */
export async function precacheConversationAudio(
  conversationId: string,
  signal?: AbortSignal,
): Promise<void> {
  try {
    await fetchWithAuth(`/v1/sync/audio/${conversationId}/precache`, {
      method: 'POST',
      signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return; // Silently return for aborted requests
    }
    console.error('Error pre-caching audio:', error);
  }
}

/**
 * Get auth headers for audio streaming
 * Used when streaming audio directly from API (fallback when signed URLs unavailable)
 */
export async function getAudioAuthHeaders(): Promise<Record<string, string>> {
  const token = await getIdToken();
  if (!token) {
    throw new Error('Not authenticated');
  }
  return {
    Authorization: `Bearer ${token}`,
  };
}

/**
 * Fetch audio file and return a Blob URL for playback
 * This works around the HTML <audio> element's inability to send custom headers
 * @param conversationId - The conversation ID
 * @param audioFileId - The audio file ID
 * @returns Blob URL that can be used as audio src
 */
export async function fetchAudioBlob(
  conversationId: string,
  audioFileId: string,
): Promise<string> {
  const headers = await getAudioAuthHeaders();
  const url = getAudioStreamUrl(conversationId, audioFileId);

  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Failed to fetch audio: ${response.status} ${response.statusText}`);
  }

  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

// ============================================================================
// Folders API
// ============================================================================

import type {
  Folder,
  CreateFolderRequest,
  UpdateFolderRequest,
  BulkMoveConversationsRequest,
} from '@/types/folder';

/**
 * Map backend folder to frontend format (icon -> emoji)
 */
function mapFolderResponse(folder: Folder): Folder {
  return {
    ...folder,
    emoji: folder.icon || folder.emoji, // Map icon to emoji for display
  };
}

/**
 * Get all folders for the current user
 */
export async function getFolders(): Promise<Folder[]> {
  try {
    const folders = await fetchWithAuth<Folder[]>('/v1/folders');
    return folders.map(mapFolderResponse);
  } catch {
    return [];
  }
}

/**
 * Create a new folder
 */
export async function createFolder(data: CreateFolderRequest): Promise<Folder> {
  const folder = await fetchWithAuth<Folder>('/v1/folders', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  invalidateCache(invalidationPatterns.folders);
  return mapFolderResponse(folder);
}

/**
 * Update an existing folder
 */
export async function updateFolder(
  folderId: string,
  data: UpdateFolderRequest,
): Promise<Folder> {
  const folder = await fetchWithAuth<Folder>(`/v1/folders/${folderId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  invalidateCache(invalidationPatterns.folders);
  return mapFolderResponse(folder);
}

/**
 * Delete a folder
 * Conversations in the folder are moved back to "All"
 */
export async function deleteFolder(folderId: string): Promise<void> {
  await fetchWithAuth(`/v1/folders/${folderId}`, {
    method: 'DELETE',
  });
  invalidateCache(invalidationPatterns.folders);
  invalidateCache(invalidationPatterns.conversations); // Conversations move back to "All"
}

/**
 * Bulk move multiple conversations to a folder
 * @param folderId - The target folder ID
 * @param conversationIds - Array of conversation IDs to move
 */
export async function bulkMoveConversationsToFolder(
  folderId: string,
  conversationIds: string[],
): Promise<void> {
  await fetchWithAuth(`/v1/folders/${folderId}/conversations/bulk-move`, {
    method: 'POST',
    body: JSON.stringify({ conversation_ids: conversationIds }),
  });
}

// ============================================================================
// FCM Token Registration API
// ============================================================================

/**
 * Register FCM token for push notifications
 * This is the same endpoint used by the mobile app
 * @param fcmToken - The FCM registration token
 */
export async function registerFCMToken(fcmToken: string): Promise<void> {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const deviceIdHash = await getWebDeviceIdHash();
  if (!deviceIdHash) return;

  await fetchWithAuth('/v1/users/fcm-token', {
    method: 'POST',
    headers: {
      'X-App-Platform': 'web',
      'X-Device-Id-Hash': deviceIdHash,
    },
    body: JSON.stringify({
      fcm_token: fcmToken,
      time_zone: timeZone,
    }),
  });
}

/**
 * Unregister FCM token (called on sign out)
 * @param fcmToken - The FCM registration token to remove
 */
export async function unregisterFCMToken(fcmToken: string): Promise<void> {
  try {
    const deviceIdHash = await getWebDeviceIdHash();
    if (!deviceIdHash) return;

    await fetchWithAuth('/v1/users/fcm-token', {
      method: 'DELETE',
      headers: {
        'X-App-Platform': 'web',
        'X-Device-Id-Hash': deviceIdHash,
      },
      body: JSON.stringify({
        fcm_token: fcmToken,
      }),
    });
  } catch (error) {
    // Silently fail on logout - token cleanup is best-effort
    console.warn('Failed to unregister FCM token:', error);
  }
}

// ============================================================================
// Fair Use Status
// ============================================================================

/**
 * Client-narrowed view of the generated `FairUseStatusResponse` (backend
 * OpenAPI authority for `/v1/fair-use/status`). The backend types `stage` as a
 * plain string; this adapter narrows it to the union the UI renders.
 */
export type FairUseStatus = Omit<FairUseStatusResponse, 'stage'> & {
  stage: 'none' | 'warning' | 'throttle' | 'restrict';
};

export async function getFairUseStatus(): Promise<FairUseStatus | null> {
  try {
    return await fetchWithAuth<FairUseStatus>('/v1/fair-use/status');
  } catch (error) {
    console.error('getFairUseStatus error:', error);
    return null;
  }
}
