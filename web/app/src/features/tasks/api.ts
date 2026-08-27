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
import type { ActionItem } from '@/types/conversation';
import type { ActionItemsResponse } from '@/lib/omiApi.generated';
export type { ActionItemsResponse };

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
