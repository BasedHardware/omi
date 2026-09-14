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
import { getMemoryBackendScope, memoryCacheScopeKey } from '@/lib/cache';

export function MemoriesPrefetcher() {
  const { user, loading } = useAuth();
  const prefetchedScopeRef = useRef<string | null>(null);
  const backendScope = getMemoryBackendScope();
  const scope = !loading && user ? { ownerId: user.uid, backendScope } : null;
  const scopeKey = scope ? memoryCacheScopeKey(scope) : null;

  useEffect(() => {
    // Only run once per authenticated owner/backend session.
    if (loading || !scope || !scopeKey) return;
    if (prefetchedScopeRef.current === scopeKey) return;
    prefetchedScopeRef.current = scopeKey;

    const prefetchMemories = async () => {
      try {
        // Check if we already have fresh cache
        const cacheFresh = await isCacheFresh(scope);
        if (cacheFresh) {
          console.log('[MemoriesPrefetcher] Cache is fresh, skipping prefetch');
          return;
        }

        console.log('[MemoriesPrefetcher] Starting background prefetch...');

        // Fetch memories in the background (backend returns up to 5000 when offset=0)
        const memories = await getMemories({ limit: 25, offset: 0 });

        // Cache them in IndexedDB
        await cacheMemories(memories, 'useful_now', scope);

        console.log(`[MemoriesPrefetcher] Prefetched ${memories.length} memories`);
      } catch (error) {
        prefetchedScopeRef.current = null;
        // Silent fail - prefetching is a nice-to-have
        console.error('[MemoriesPrefetcher] Failed to prefetch:', error);
      }
    };

    // Run prefetch after a small delay to not block initial page load
    const timeout = setTimeout(prefetchMemories, 2000);

    return () => clearTimeout(timeout);
  }, [loading, scope, scopeKey]);

  // This component doesn't render anything
  return null;
}
