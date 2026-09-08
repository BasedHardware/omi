'use client';

import { useEffect, useMemo } from 'react';
import { createResource, createSignal, type Resource } from '@tschk/moonshine';
import { useResourceValue } from '@/lib/signals';

export interface AsyncResource<T> {
  data: T | undefined;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export interface AsyncResourceOptions {
  /** Hold at idle and skip fetching — e.g. nothing selected yet. */
  enabled?: boolean;
  fallbackMessage?: string;
}

/**
 * Load a value and expose it with its loading and error state.
 *
 * Backed by moonshine's `createResource`, so the request and its state live in
 * signals outside React and the component subscribes through
 * `useSyncExternalStore`. No React state is set from an effect, so a response
 * arriving after unmount updates a signal nobody reads rather than needing a
 * mounted-flag guard — and the whole `react-hooks/set-state-in-effect` class
 * does not arise here.
 *
 * `key` identifies the request: change it and a new resource is built and
 * fetched. `fetcher` is read fresh at call time, so it need not be memoized.
 */
export function useAsyncResource<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  options: AsyncResourceOptions = {},
): AsyncResource<T> {
  const { enabled = true, fallbackMessage = 'Request failed' } = options;
  const active = enabled && key !== null;

  // The current fetcher lives in a signal rather than a React ref: the resource
  // reads it when the request actually runs, which is outside render, and a
  // signal makes that explicit instead of looking like a ref read during render.
  // Seeded with the first fetcher so the initial request is correct.
  const latestFetcher = useMemo(() => createSignal(fetcher), []);
  useEffect(() => {
    latestFetcher.set(() => fetcher);
  }, [latestFetcher, fetcher]);

  // Rebuilt only when the key or enablement flips, so re-rendering never
  // starts a second fetch. An inactive slot still needs a Resource to
  // subscribe to, so it gets one that never runs.
  const resource = useMemo<Resource<T>>(
    () => createResource<T>(() => latestFetcher.peek()(), { immediate: false }),
    // `key` and `active` are cache keys, not values the factory reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, active],
  );

  const { data, loading, error, refetch } = useResourceValue(resource);

  // Kicked off here rather than via `immediate: true` at construction: useMemo
  // may run more than once per commit (StrictMode renders twice), and firing
  // the request from the factory would fetch once per discarded store.
  // Writing signals from an effect is fine — no React state is set.
  useEffect(() => {
    if (active) void resource.refetch();
  }, [active, resource]);

  return {
    data,
    loading: active && loading,
    error: error ? error.message || fallbackMessage : null,
    refresh: async () => {
      await refetch();
    },
  };
}
