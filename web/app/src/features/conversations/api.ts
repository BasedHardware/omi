import { getIdToken } from '@/lib/firebase';
import { getWebDeviceIdHash } from '@/lib/clientDevice';
import {
  invalidateCache,
  invalidateCacheKey,
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
import type {
  Conversation,
  ConversationScreenFrameSet,
  ConversationSearchResponse,
  ConversationStatus,
  AudioFileUrlInfo,
  ScreenFrameSharingUpdateRequest,
} from '@/types/conversation';
import type {
  MergeConversationsResponse,
  CreateConversationResponse,
} from '@/lib/omiApi.generated';
export type { MergeConversationsResponse, CreateConversationResponse };
import type { DailySummary } from '@/types/recap';
import type { Person } from '@/types/user';
import type { Folder, CreateFolderRequest, UpdateFolderRequest } from '@/types/folder';

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
 * Reprocess a conversation (rebuild summary/search after transcript edits)
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

export { getAudioAuthHeaders } from '@/shared/api/client';

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
