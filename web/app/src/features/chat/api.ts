import { getIdToken } from '@/lib/firebase';
import { getWebDeviceIdHash } from '@/lib/clientDevice';
import {
  invalidateCache,
  invalidationPatterns,
  fetchWithCache,
  cacheKeys,
  CACHE_TTL,
} from '@/lib/cache';
import {
  API_BASE_URL,
  fetchAuthorizedBlob,
  fetchWithAuth,
  getAudioAuthHeaders,
} from '@/shared/api/client';
import type { ServerMessage, MessageChunk, MessageFile } from '@/types/conversation';
import type { ChatSession } from '@/types/chatSessions';
import { parseStreamLine } from './model';
export { parseStreamLine };

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
