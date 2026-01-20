/**
 * MemoriesPrefetcher
 *
 * Prefetches memories in the background when the user logs in.
 * This ensures that when the user navigates to the memories page,
 * data is already cached in IndexedDB for instant loading.
 *
 * Benefits:
 * - Perceived load time: 0ms (data already cached)
 * - Works in the background without blocking UI
 * - Only runs once per session
 */

'use client';

import { useEffect, useRef } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { getMemories } from '@/lib/api';
import { cacheMemories, isCacheFresh } from '@/lib/indexeddb';

export function MemoriesPrefetcher() {
  const { user } = useAuth();
  const prefetchedRef = useRef(false);

  useEffect(() => {
    // Only run once per session
    if (prefetchedRef.current) return;
    if (!user) return;

    const prefetchMemories = async () => {
      try {
        // Check if we already have fresh cache
        const cacheFresh = await isCacheFresh();
        if (cacheFresh) {
          console.log('[MemoriesPrefetcher] Cache is fresh, skipping prefetch');
          return;
        }

        console.log('[MemoriesPrefetcher] Starting background prefetch...');

        // Fetch memories in the background (backend returns up to 5000 when offset=0)
        const memories = await getMemories({ limit: 25, offset: 0 });

        // Cache them in IndexedDB
        await cacheMemories(memories);

        console.log(`[MemoriesPrefetcher] Prefetched ${memories.length} memories`);
        prefetchedRef.current = true;
      } catch (error) {
        // Silent fail - prefetching is a nice-to-have
        console.error('[MemoriesPrefetcher] Failed to prefetch:', error);
      }
    };

    // Run prefetch after a small delay to not block initial page load
    const timeout = setTimeout(prefetchMemories, 2000);

    return () => clearTimeout(timeout);
  }, [user]);

  // This component doesn't render anything
  return null;
}
