'use client';

import { useMemo } from 'react';
import { getActionItems, getConversations, getMemories } from '@/lib/api';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import type { HubStatCounts } from '@/components/home/HubStatRibbon';

/** One page. A full page only proves a floor, which the ribbon renders as "100+". */
const PAGE = 100;

/**
 * Counts for the hub stat ribbon.
 *
 * Each source is read independently so one slow or failing endpoint does not
 * hold up the others; a cell that has not resolved stays `null` and renders an
 * em-dash rather than a 0, because a 0 is a claim about the user's data.
 */
export function useHubStats(): HubStatCounts {
  const conversations = useAsyncResource('hub:conversations', () =>
    getConversations({ limit: PAGE }),
  );
  const tasks = useAsyncResource('hub:tasks', () => getActionItems({ limit: PAGE }));
  const memories = useAsyncResource('hub:memories', () => getMemories({ limit: PAGE }));

  return useMemo(
    () => ({
      conversations: conversations.data?.length ?? null,
      conversationsAtLeast: (conversations.data?.length ?? 0) >= PAGE,
      tasks: tasks.data?.items.length ?? null,
      memories: memories.data?.length ?? null,
    }),
    [conversations.data, tasks.data, memories.data],
  );
}
