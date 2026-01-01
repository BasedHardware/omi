import { getIdToken } from './firebase';
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
} from '@/types/conversation';

// Use proxy in development to avoid CORS, direct API in production
const isDevelopment = process.env.NODE_ENV === 'development';
const API_BASE_URL = isDevelopment
  ? '/api/proxy'  // Next.js API route proxy
  : (process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me');

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
  console.log('Fetching:', url);

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
      console.error('API error response:', response.status, errorText);

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
export async function getConversation(id: string): Promise<Conversation> {
  return fetchWithAuth<Conversation>(`/v1/conversations/${id}`);
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
  await fetchWithAuth(`/v1/conversations/${id}/starred`, {
    method: 'PATCH',
    body: JSON.stringify({ starred }),
  });
}

/**
 * Delete a conversation
 */
export async function deleteConversation(id: string): Promise<void> {
  await fetchWithAuth(`/v1/conversations/${id}`, {
    method: 'DELETE',
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
  return fetchWithAuth<Memory>('/v3/memories', {
    method: 'POST',
    body: JSON.stringify({
      content: params.content,
      visibility: params.visibility || 'public',
      category: params.category || 'manual',
    }),
  });
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
}

/**
 * Delete a memory
 */
export async function deleteMemory(id: string): Promise<void> {
  await fetchWithAuth(`/v3/memories/${id}`, {
    method: 'DELETE',
  });
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

export interface App {
  id: string;
  name: string;
  description: string;
  image?: string;
  author?: string;
  capabilities: string[];
  category?: string;
  enabled: boolean;
  deleted: boolean;
  installs?: number;
  rating_avg?: number;
  rating_count?: number;
  private?: boolean;
}

interface AppsSearchResponse {
  apps: App[];
}

/**
 * Get apps with optional filters
 */
export async function getApps(params: {
  installed?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<App[]> {
  const { installed, limit = 50, offset = 0 } = params;

  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  if (installed !== undefined) {
    queryParams.set('installed_apps', installed.toString());
  }

  const response = await fetchWithAuth<AppsSearchResponse>(`/v2/apps?${queryParams}`);
  return response.apps || [];
}

/**
 * Get chat-enabled apps (apps with 'chat' or 'persona' capability)
 */
export async function getChatApps(): Promise<App[]> {
  const apps = await getApps({ installed: true });
  return apps.filter(app =>
    app.capabilities?.includes('chat') || app.capabilities?.includes('persona')
  );
}
