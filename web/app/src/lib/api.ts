import { getIdToken } from './firebase';
import { invalidateCache, invalidationPatterns } from './cache';
import type {
  Conversation,
  ConversationSearchResponse,
  ConversationStatus,
  ActionItem,
  Memory,
  MemoryCategory,
  MemoryVisibility,
  KnowledgeGraph,
  ServerMessage,
  MessageChunk,
  MessageChunkType,
  MessageFile,
  AudioFileUrlInfo,
} from '@/types/conversation';
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
  AppApiKey,
} from '@/types/apps';

// Always use proxy to avoid CORS (browser → proxy → api.omi.me)
const API_BASE_URL = '/api/proxy';

/**
 * Make an authenticated API request
 */
async function fetchWithAuth<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
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

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
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
      throw new Error('Network error: Unable to reach the API. Please check your connection.');
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
  params: GetConversationsParams = {}
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
 */
// Simple cache for getConversation to avoid duplicate requests
const conversationCache = new Map<string, { data: Conversation; timestamp: number }>();
const pendingRequests = new Map<string, Promise<Conversation>>();
const CACHE_TTL = 60000; // 1 minute cache

export async function getConversation(id: string): Promise<Conversation> {
  // Check cache first
  const cached = conversationCache.get(id);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }

  // Check if there's already a pending request for this ID (deduplicate in-flight requests)
  const pending = pendingRequests.get(id);
  if (pending) {
    return pending;
  }

  // Make the request and cache it
  const request = fetchWithAuth<Conversation>(`/v1/conversations/${id}`).then(data => {
    conversationCache.set(id, { data, timestamp: Date.now() });
    pendingRequests.delete(id);
    return data;
  }).catch(err => {
    pendingRequests.delete(id);
    throw err;
  });

  pendingRequests.set(id, request);
  return request;
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
  params: SearchConversationsParams
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
export async function toggleStarred(
  id: string,
  starred: boolean
): Promise<void> {
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

/**
 * Merge multiple conversations into one
 * @param conversationIds - Array of conversation IDs to merge
 * @param reprocess - Whether to reprocess the merged conversation (default: true)
 * @returns Response with status and merged conversation IDs
 */
export interface MergeConversationsResponse {
  status: string;
  message: string;
  warning?: string;
  conversation_ids: string[];
}

export async function mergeConversations(
  conversationIds: string[],
  reprocess: boolean = true
): Promise<MergeConversationsResponse> {
  return fetchWithAuth<MergeConversationsResponse>('/v1/conversations/merge', {
    method: 'POST',
    body: JSON.stringify({
      conversation_ids: conversationIds,
      reprocess,
    }),
  });
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

interface ActionItemsResponse {
  action_items: ActionItem[];
  has_more: boolean;
}

export async function getActionItems(
  params: GetActionItemsParams = {}
): Promise<{ items: ActionItem[]; hasMore: boolean }> {
  const { limit = 100, offset = 0, completed } = params;

  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  if (completed !== undefined) {
    queryParams.set('completed', completed.toString());
  }

  const response = await fetchWithAuth<ActionItemsResponse>(`/v1/action-items?${queryParams}`);

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
  params: CreateActionItemParams
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
  completed: boolean
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
  due_at: string | null
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
  description: string
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

export async function getMemories(
  params: GetMemoriesParams = {}
): Promise<Memory[]> {
  const { limit = 100, offset = 0, categories } = params;

  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  if (categories && categories.length > 0) {
    queryParams.set('categories', categories.join(','));
  }

  return fetchWithAuth<Memory[]>(`/v3/memories?${queryParams}`);
}

/**
 * Create a new memory
 */
export interface CreateMemoryParams {
  content: string;
  visibility?: MemoryVisibility;
  category?: MemoryCategory;
}

export async function createMemory(
  params: CreateMemoryParams
): Promise<Memory> {
  const memory = await fetchWithAuth<Memory>('/v3/memories', {
    method: 'POST',
    body: JSON.stringify({
      content: params.content,
      visibility: params.visibility || 'public',
      category: params.category || 'manual',
    }),
  });
  invalidateCache(invalidationPatterns.memories);
  return memory;
}

/**
 * Update memory content
 */
export async function updateMemoryContent(
  id: string,
  content: string
): Promise<void> {
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
  visibility: MemoryVisibility
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
 * Review a memory (accept or reject)
 */
export async function reviewMemory(
  id: string,
  accept: boolean
): Promise<void> {
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

/**
 * Trigger knowledge graph rebuild
 */
export async function rebuildKnowledgeGraph(): Promise<void> {
  await fetchWithAuth('/v1/knowledge-graph/rebuild', {
    method: 'POST',
  });
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
export async function getMessages(appId?: string): Promise<ServerMessage[]> {
  const queryParams = new URLSearchParams();
  if (appId) {
    queryParams.set('app_id', appId);
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
    fileIds?: string[];
    context?: {
      type: string;
      id?: string;
      title?: string;
      summary?: string;
    } | null;
  }
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

  const url = `${API_BASE_URL}/v2/messages${queryParams.toString() ? `?${queryParams}` : ''}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
      file_ids: options?.fileIds || [],
      context: options?.context || null,
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
export async function clearMessages(appId?: string): Promise<void> {
  const queryParams = new URLSearchParams();
  if (appId) {
    queryParams.set('app_id', appId);
  }

  const endpoint = `/v2/messages${queryParams.toString() ? `?${queryParams}` : ''}`;
  await fetchWithAuth(endpoint, {
    method: 'DELETE',
  });
}

/**
 * Get initial greeting message from an app
 */
export async function getInitialMessage(appId: string): Promise<ServerMessage> {
  return fetchWithAuth<ServerMessage>(`/v2/initial-message?app_id=${appId}`, {
    method: 'POST',
  });
}

/**
 * Upload files for chat
 */
export async function uploadChatFiles(
  files: File[],
  appId?: string
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
      'Authorization': `Bearer ${token}`,
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
  // API expects field name 'files' (matching mobile app)
  formData.append('files', audioBlob, 'audio.wav');

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
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
export async function getAppsGrouped(params: {
  capability?: string;
  offset?: number;
  limit?: number;
} = {}): Promise<AppsGroupedResponse> {
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
export async function searchApps(params: AppsSearchParams = {}): Promise<AppsSearchResponse> {
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
  return response.data.filter(app =>
    app.capabilities?.includes('chat') || app.capabilities?.includes('persona')
  );
}

// ============================================================================
// App Creation/Editing API
// ============================================================================

/**
 * Create a new app
 */
export async function createApp(
  data: CreateAppRequest & { deleted?: boolean; price?: number; thumbnails?: string[]; uid?: string },
  imageFile?: File
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
      'Authorization': `Bearer ${token}`,
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
  imageFile?: File
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
      'Authorization': `Bearer ${token}`,
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
 * Delete an app
 */
export async function deleteApp(appId: string): Promise<void> {
  await fetchWithAuth(`/v1/apps/${appId}`, {
    method: 'DELETE',
  });
}

/**
 * Change app visibility (public/private)
 */
export async function changeAppVisibility(
  appId: string,
  isPrivate: boolean
): Promise<void> {
  await fetchWithAuth(`/v1/apps/${appId}/change-visibility?private=${isPrivate}`, {
    method: 'PATCH',
  });
}

/**
 * Upload app thumbnail
 */
export async function uploadAppThumbnail(
  file: File
): Promise<ThumbnailUploadResponse> {
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
      'Authorization': `Bearer ${token}`,
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
  currentDescription: string
): Promise<string> {
  const response = await fetchWithAuth<GenerateDescriptionResponse>('/v1/app/generate-description', {
    method: 'POST',
    body: JSON.stringify({ name, description: currentDescription }),
  });
  return response.description;
}

/**
 * Generate app description and emoji using AI
 * Used for quick template creation (matches mobile app behavior)
 */
export async function generateAppDescriptionAndEmoji(
  name: string,
  prompt: string
): Promise<{ description: string; emoji: string }> {
  try {
    const response = await fetchWithAuth<{ description: string; emoji: string }>(
      '/v1/app/generate-description-emoji',
      {
        method: 'POST',
        body: JSON.stringify({ name, prompt }),
      }
    );
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

    const response = await fetch(`${API_BASE_URL}/v1/apps/proactive-notification-scopes`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

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
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

/**
 * Get API keys for an app
 */
export async function getAppApiKeys(appId: string): Promise<AppApiKey[]> {
  return fetchWithAuth<AppApiKey[]>(`/v1/apps/${appId}/api-keys`);
}

/**
 * Create new API key for an app
 */
export async function createAppApiKey(appId: string): Promise<AppApiKey> {
  return fetchWithAuth<AppApiKey>(`/v1/apps/${appId}/api-keys`, {
    method: 'POST',
  });
}

/**
 * Delete API key for an app
 */
export async function deleteAppApiKey(appId: string, keyId: string): Promise<void> {
  await fetchWithAuth(`/v1/apps/${appId}/api-keys/${keyId}`, {
    method: 'DELETE',
  });
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
  PrivateCloudSync,
  UserUsage,
  UserUsageResponse,
  UsageStats,
  AllUsageData,
  UserSubscription,
  UserSubscriptionResponse,
  Person,
} from '@/types/user';

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
export async function updateDailySummarySettings(settings: DailySummarySettings): Promise<void> {
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
  params: GetDailySummariesParams = {}
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

/**
 * Update transcription preferences
 */
export async function updateTranscriptionPreferences(
  preferences: Partial<TranscriptionPreferences>
): Promise<void> {
  await fetchWithAuth('/v1/users/transcription-preferences', {
    method: 'PATCH',
    body: JSON.stringify(preferences),
  });
}

// Webhook type enum matching backend API
type WebhookType = 'memory_created' | 'realtime_transcript' | 'audio_bytes' | 'day_summary';

/**
 * Get developer webhook URL
 */
export async function getDeveloperWebhook(
  type: WebhookType
): Promise<WebhookSettings> {
  return fetchWithAuth<WebhookSettings>(`/v1/users/developer/webhook/${type}`);
}

/**
 * Set developer webhook URL
 */
export async function setDeveloperWebhook(
  type: WebhookType,
  url: string
): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/**
 * Enable developer webhook
 */
export async function enableDeveloperWebhook(
  type: WebhookType
): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}/enable`, {
    method: 'POST',
  });
}

/**
 * Disable developer webhook
 */
export async function disableDeveloperWebhook(
  type: WebhookType
): Promise<void> {
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
 * Delete recording permission and all stored recordings
 */
export async function deleteRecordingPermission(): Promise<void> {
  await fetchWithAuth('/v1/users/store-recording-permission', {
    method: 'DELETE',
  });
}

/**
 * Get private cloud sync status
 */
export async function getPrivateCloudSync(): Promise<PrivateCloudSync> {
  return fetchWithAuth<PrivateCloudSync>('/v1/users/private-cloud-sync');
}

/**
 * Set private cloud sync
 */
export async function setPrivateCloudSync(enabled: boolean): Promise<void> {
  await fetchWithAuth(`/v1/users/private-cloud-sync?value=${enabled}`, {
    method: 'POST',
  });
}

/**
 * Get user usage stats for a specific period
 */
export async function getUserUsage(period: 'today' | 'monthly' | 'yearly' | 'all_time' = 'monthly'): Promise<UserUsage | null> {
  try {
    const response = await fetchWithAuth<UserUsageResponse>(`/v1/users/me/usage?period=${period}`);

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
    const response = await fetchWithAuth<UserSubscriptionResponse>('/v1/users/me/subscription');

    const result: UserSubscription = {
      plan: response.subscription?.plan || 'basic',
      status: response.subscription?.status || 'active',
      is_unlimited: response.subscription?.plan === 'unlimited',
      current_period_end: response.subscription?.current_period_end,
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
    const response = await fetchWithAuth<AvailablePlansResponse>('/v1/payments/available-plans');
    return response;
  } catch (error) {
    console.error('getAvailablePlans error:', error);
    return null;
  }
}

/**
 * Create a checkout session for subscription
 */
export async function createCheckoutSession(priceId: string): Promise<CheckoutSessionResponse | null> {
  try {
    const response = await fetchWithAuth<CheckoutSessionResponse>('/v1/payments/checkout-session', {
      method: 'POST',
      body: JSON.stringify({ price_id: priceId }),
    });
    return response;
  } catch (error) {
    console.error('createCheckoutSession error:', error);
    return null;
  }
}

/**
 * Upgrade subscription to a different plan
 */
export async function upgradeSubscription(priceId: string): Promise<UpgradeSubscriptionResponse | null> {
  try {
    const response = await fetchWithAuth<UpgradeSubscriptionResponse>('/v1/payments/upgrade-subscription', {
      method: 'POST',
      body: JSON.stringify({ price_id: priceId }),
    });
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
    const response = await fetchWithAuth<CancelSubscriptionResponse>('/v1/payments/subscription', {
      method: 'DELETE',
    });
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
    const response = await fetchWithAuth<CustomerPortalResponse>('/v1/payments/customer-portal', {
      method: 'POST',
    });
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
  options: { isUser?: boolean; personId?: string | null }
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
export async function createDeveloperApiKey(name: string, scopes?: string[]): Promise<DeveloperApiKey> {
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
 * Export all conversations as JSON
 */
export async function exportAllData(): Promise<{ conversations: unknown[] }> {
  return fetchWithAuth<{ conversations: unknown[] }>('/v1/conversations?limit=10000&offset=0');
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
    const result = await fetchWithAuth<TranscriptionPreferences>('/v1/users/transcription-preferences');
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
  { id: 'google_calendar', appKey: 'google_calendar', name: 'Google Calendar', description: 'Sync with your calendar', logo: '/integrations/google-calendar.png' },
  { id: 'whoop', appKey: 'whoop', name: 'Whoop', description: 'Health & fitness tracking', logo: '/integrations/whoop.png' },
  { id: 'notion', appKey: 'notion', name: 'Notion', description: 'Sync notes to Notion', logo: '/integrations/notion-logo.png' },
  { id: 'github', appKey: 'github', name: 'GitHub', description: 'Create issues and notes', logo: '/integrations/github-logo.png' },
  { id: 'twitter', appKey: 'twitter', name: 'X (Twitter)', description: 'Share to Twitter', logo: '/integrations/x-logo.avif' },
  { id: 'gmail', appKey: 'gmail', name: 'Gmail', description: 'Email integrations', logo: '/integrations/gmail-logo.jpeg', coming_soon: true },
];

/**
 * Get individual integration connection status (like mobile app)
 */
async function getIntegrationStatus(appKey: string): Promise<{ connected: boolean }> {
  try {
    const response = await fetchWithAuth<{ connected: boolean; app_key: string }>(`/v1/integrations/${appKey}`);
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
export async function getIntegrationOAuthUrl(integrationId: string): Promise<string | null> {
  try {
    const response = await fetchWithAuth<{ auth_url: string }>(`/v1/integrations/${integrationId}/oauth-url`);
    return response.auth_url || null;
  } catch {
    return null;
  }
}

/**
 * Connect an integration (alternative method)
 */
export async function connectIntegration(integrationId: string): Promise<{ redirect_url: string }> {
  return fetchWithAuth<{ redirect_url: string }>(`/v1/integrations/${integrationId}/connect`, {
    method: 'POST',
  });
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
  appId?: string
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
  title: string
): Promise<void> {
  await fetchWithAuth(`/v1/conversations/${conversationId}/title?title=${encodeURIComponent(title)}`, {
    method: 'PATCH',
  });
}

/**
 * Test a custom prompt against a conversation
 * @param conversationId - The ID of the conversation
 * @param prompt - The custom prompt to test
 * @returns The generated summary
 */
export async function testConversationPrompt(
  conversationId: string,
  prompt: string
): Promise<string> {
  const response = await fetchWithAuth<{ summary: string }>(
    `/v1/conversations/${conversationId}/test-prompt`,
    {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }
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
  format: string = 'wav'
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
  signal?: AbortSignal
): Promise<AudioFileUrlInfo[]> {
  try {
    const response = await fetchWithAuth<{ audio_files: AudioFileUrlInfo[] }>(
      `/v1/sync/audio/${conversationId}/urls`,
      { signal }
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
 * Pre-cache audio files for a conversation
 * Triggers background caching of audio files for faster playback
 * @param conversationId - The conversation ID
 */
export async function precacheConversationAudio(
  conversationId: string,
  signal?: AbortSignal
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
    'Authorization': `Bearer ${token}`,
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
  audioFileId: string
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
  ReorderFoldersRequest,
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
  data: UpdateFolderRequest
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
 * Move a single conversation to a folder
 * @param conversationId - The conversation to move
 * @param folderId - The target folder ID, or null to remove from folder
 */
export async function moveConversationToFolder(
  conversationId: string,
  folderId: string | null
): Promise<void> {
  await fetchWithAuth(`/v1/conversations/${conversationId}/folder`, {
    method: 'PATCH',
    body: JSON.stringify({ folder_id: folderId }),
  });
  invalidateCache(invalidationPatterns.conversations);
}

/**
 * Bulk move multiple conversations to a folder
 * @param folderId - The target folder ID
 * @param conversationIds - Array of conversation IDs to move
 */
export async function bulkMoveConversationsToFolder(
  folderId: string,
  conversationIds: string[]
): Promise<void> {
  await fetchWithAuth(`/v1/folders/${folderId}/conversations/bulk-move`, {
    method: 'POST',
    body: JSON.stringify({ conversation_ids: conversationIds }),
  });
}

/**
 * Reorder folders
 * @param folderIds - Array of folder IDs in the desired order
 */
export async function reorderFolders(folderIds: string[]): Promise<void> {
  await fetchWithAuth('/v1/folders/reorder', {
    method: 'POST',
    body: JSON.stringify({ folder_ids: folderIds }),
  });
}

// ============================================================================
// FCM Token Registration API
// ============================================================================

const WEB_DEVICE_ID_KEY = 'omi-web-device-id';

/**
 * Get or generate a unique device ID for this browser
 * This is used to identify the device when registering FCM tokens
 */
function getWebDeviceIdHash(): string {
  if (typeof window === 'undefined') return 'server';

  let deviceId = localStorage.getItem(WEB_DEVICE_ID_KEY);
  if (!deviceId) {
    // Generate a unique ID for this browser
    deviceId = `web_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
    localStorage.setItem(WEB_DEVICE_ID_KEY, deviceId);
  }

  // Create a simple hash of the device ID
  let hash = 0;
  for (let i = 0; i < deviceId.length; i++) {
    const char = deviceId.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash).toString(16);
}

/**
 * Register FCM token for push notifications
 * This is the same endpoint used by the mobile app
 * @param fcmToken - The FCM registration token
 */
export async function registerFCMToken(fcmToken: string): Promise<void> {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const deviceIdHash = getWebDeviceIdHash();

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
    const deviceIdHash = getWebDeviceIdHash();

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
