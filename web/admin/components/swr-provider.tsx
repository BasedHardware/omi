'use client';

import { SWRConfig } from 'swr';
import { ReactNode, useMemo } from 'react';

// localStorage-backed SWR cache provider. On first render we rehydrate
// any previously-cached responses so the dashboard paints instantly with
// stale data, then SWR revalidates in the background. Every mutation of
// the cache is mirrored back to localStorage inside a microtask so we
// don't block renders on writes.
//
// We cap each entry at ~1MB and the total payload at ~5MB, because the
// iOS/desktop webkit localStorage quota is 5MB per origin.
const STORAGE_KEY = 'omi-admin-swr-cache-v5';
const MAX_ENTRY_BYTES = 1_000_000;
const MAX_TOTAL_BYTES = 5_000_000;

type CacheEntry = { data: unknown; error: unknown; isValidating: boolean; isLoading: boolean };

function createLocalStorageProvider(): Map<string, CacheEntry> {
  if (typeof window === 'undefined') {
    return new Map();
  }

  let hydrated: [string, CacheEntry][] = [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) hydrated = JSON.parse(raw);
  } catch (err) {
    console.warn('SWR cache rehydrate failed:', err);
  }

  const map = new Map<string, CacheEntry>(hydrated);

  let persistScheduled = false;
  const schedulePersist = () => {
    if (persistScheduled) return;
    persistScheduled = true;
    queueMicrotask(() => {
      persistScheduled = false;
      try {
        // Only persist entries that actually carry data, skip errored /
        // in-flight entries and anything too large to fit in the quota.
        const entries: [string, CacheEntry][] = [];
        let totalBytes = 0;
        map.forEach((value, key) => {
          if (totalBytes >= MAX_TOTAL_BYTES) return;
          if (value == null || value.error != null || value.data == null) return;
          const serialized = JSON.stringify([key, { data: value.data }]);
          if (serialized.length > MAX_ENTRY_BYTES) return;
          if (totalBytes + serialized.length > MAX_TOTAL_BYTES) return;
          entries.push([key, { data: value.data, error: null, isValidating: false, isLoading: false }]);
          totalBytes += serialized.length;
        });
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
      } catch (err) {
        // Quota exceeded, invalid JSON, etc. — silently drop the cache.
        try {
          window.localStorage.removeItem(STORAGE_KEY);
        } catch {
          /* noop */
        }
      }
    });
  };

  // Patch the mutating Map methods to schedule a persist.
  const originalSet = map.set.bind(map);
  map.set = (key, value) => {
    originalSet(key, value);
    schedulePersist();
    return map;
  };
  const originalDelete = map.delete.bind(map);
  map.delete = (key) => {
    const result = originalDelete(key);
    if (result) schedulePersist();
    return result;
  };

  return map;
}

export function SWRProvider({ children }: { children: ReactNode }) {
  const provider = useMemo(() => {
    const cache = createLocalStorageProvider();
    return () => cache;
  }, []);

  return (
    <SWRConfig
      value={{
        provider,
        errorRetryCount: 3,
        errorRetryInterval: 3000,
        dedupingInterval: 5000,
        revalidateOnReconnect: true,
        // Revalidate on mount so the stale cached data gets refreshed
        // in the background; SWR will show the cached value immediately.
        revalidateOnMount: true,
        revalidateIfStale: true,
        onErrorRetry: (error, _key, _config, revalidate, { retryCount }) => {
          // Don't retry on auth errors — re-login is needed
          if (error?.status === 401 || error?.status === 403) return;
          if (retryCount >= 3) return;
          // Exponential backoff: 2s, 4s, 8s
          setTimeout(() => revalidate({ retryCount }), Math.min(1000 * 2 ** retryCount, 30000));
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
