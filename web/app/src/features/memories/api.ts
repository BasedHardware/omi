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
import type {
  Memory,
  MemoryCategory,
  MemoryVisibility,
  KnowledgeGraph,
} from '@/types/conversation';

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
 * `@/features/memories/memoryCategory`, which mirrors how the desktop clients do it.
 */
export async function getMemories(params: GetMemoriesParams = {}): Promise<Memory[]> {
  const { limit = 100, offset = 0 } = params;

  const queryParams = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

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

export async function createMemory(params: CreateMemoryParams): Promise<Memory> {
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

/**
 * Trigger knowledge graph rebuild
 */
export async function rebuildKnowledgeGraph(): Promise<void> {
  await fetchWithAuth('/v1/knowledge-graph/rebuild', {
    method: 'POST',
  });
}

export async function deleteKnowledgeGraph(): Promise<void> {
  await fetchWithAuth('/v1/knowledge-graph', {
    method: 'DELETE',
  });
}
