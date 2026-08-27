'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import type { DailySummary, GroupedDailySummaries } from '@/types/recap';
import {
  getDailySummaries,
  getDailySummary,
  deleteDailySummary,
  generateTestDailySummary,
} from '@/features/conversations/api';
import { groupRecapsByMonth, parseLocalDay } from '@/features/conversations/model';
import { getCache, setCache, updateCache, CACHE_TTL } from '@/lib/cache';

export interface UseRecapsOptions {
  limit?: number;
}

export interface UseRecapsReturn {
  recaps: DailySummary[];
  groupedRecaps: GroupedDailySummaries;
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  removeRecap: (id: string) => Promise<boolean>;
  generateForDate: (date: string) => Promise<DailySummary | null>;
  getRecapDetail: (id: string) => Promise<DailySummary | null>;
}

const RECAPS_CACHE_KEY = 'recaps:list';

interface RecapsCacheData {
  recaps: DailySummary[];
  offset: number;
  hasMore: boolean;
}

function getFromCache(): { data: RecapsCacheData; isStale: boolean } | null {
  return getCache<RecapsCacheData>(RECAPS_CACHE_KEY);
}

function setToCache(recaps: DailySummary[], offset: number, hasMore: boolean): void {
  setCache<RecapsCacheData>(RECAPS_CACHE_KEY, { recaps, offset, hasMore }, CACHE_TTL.MEDIUM);
}

function updateCacheRecaps(updater: (recaps: DailySummary[]) => DailySummary[]): void {
  updateCache<RecapsCacheData>(RECAPS_CACHE_KEY, (data) => ({
    ...data,
    recaps: updater(data.recaps),
  }));
}

function normalizeRecapsResponse(response: unknown): DailySummary[] {
  if (Array.isArray(response)) {
    return response;
  }
  if (response && typeof response === 'object') {
    const obj = response as Record<string, unknown>;
    if (Array.isArray(obj.daily_summaries)) {
      return obj.daily_summaries as DailySummary[];
    }
    if (Array.isArray(obj.summaries)) {
      return obj.summaries as DailySummary[];
    }
    if (Array.isArray(obj.data)) {
      return obj.data as DailySummary[];
    }
  }
  return [];
}

function messageFor(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export function createRecapsStore(limit: number) {
  const cachedEntry = getFromCache();
  const recaps = createSignal<DailySummary[]>(cachedEntry?.data.recaps ?? []);
  const loading = createSignal(!cachedEntry);
  const error = createSignal<string | null>(null);
  const hasMore = createSignal(cachedEntry?.data.hasMore ?? true);
  let offset = cachedEntry?.data.offset ?? 0;
  let fetching = false;
  let initialized = false;

  const doFetch = async (currentOffset: number): Promise<DailySummary[]> => {
    return normalizeRecapsResponse(await getDailySummaries({ limit, offset: currentOffset }));
  };

  const ensureLoaded = async () => {
    if (initialized) return;
    initialized = true;

    const cached = getFromCache();
    if (cached && !cached.isStale) {
      recaps.set(cached.data.recaps);
      hasMore.set(cached.data.hasMore);
      offset = cached.data.offset;
      loading.set(false);
      return;
    }

    if (cached) {
      recaps.set(cached.data.recaps);
      hasMore.set(cached.data.hasMore);
      offset = cached.data.offset;
      loading.set(false);
    }

    if (fetching) return;
    fetching = true;
    if (!cached) {
      loading.set(true);
    }
    error.set(null);

    try {
      const result = await doFetch(0);
      recaps.set(result);
      offset = result.length;
      hasMore.set(result.length >= limit);
      setToCache(result, result.length, result.length >= limit);
    } catch (err) {
      if (!cached) {
        error.set(messageFor(err, 'Failed to load recaps'));
      }
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const loadMore = async () => {
    if (fetching || !hasMore.peek()) return;
    fetching = true;
    loading.set(true);

    try {
      const result = await doFetch(offset);
      const existingIds = new Set(recaps.peek().map((r) => r.id));
      const newRecaps = result.filter((r) => !existingIds.has(r.id));
      const updated = [...recaps.peek(), ...newRecaps];
      recaps.set(updated);
      offset += result.length;
      const nextHasMore = result.length >= limit;
      hasMore.set(nextHasMore);
      setToCache(updated, offset, nextHasMore);
    } catch (err) {
      error.set(messageFor(err, 'Failed to load more recaps'));
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const refresh = async () => {
    if (fetching) return;
    fetching = true;
    loading.set(true);
    error.set(null);

    try {
      const result = await doFetch(0);
      recaps.set(result);
      offset = result.length;
      hasMore.set(result.length >= limit);
      setToCache(result, result.length, result.length >= limit);
    } catch (err) {
      error.set(messageFor(err, 'Failed to refresh recaps'));
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const removeRecap = async (id: string): Promise<boolean> => {
    const previous = recaps.peek();
    recaps.set(previous.filter((r) => r.id !== id));
    updateCacheRecaps((current) => current.filter((r) => r.id !== id));

    try {
      await deleteDailySummary(id);
      error.set(null);
      return true;
    } catch (err) {
      recaps.set(previous);
      updateCacheRecaps(() => previous);
      error.set(messageFor(err, 'Failed to delete recap'));
      return false;
    }
  };

  const generateForDate = async (date: string): Promise<DailySummary | null> => {
    try {
      const newRecap = await generateTestDailySummary(date);
      const previous = recaps.peek();
      const updated = [newRecap, ...previous.filter((r) => r.id !== newRecap.id)];
      updated.sort(
        (a, b) => parseLocalDay(b.date).getTime() - parseLocalDay(a.date).getTime(),
      );
      recaps.set(updated);
      updateCacheRecaps(() => updated);
      error.set(null);
      return newRecap;
    } catch (err) {
      error.set(messageFor(err, 'Failed to generate recap'));
      return null;
    }
  };

  const getRecapDetail = async (id: string): Promise<DailySummary | null> => {
    try {
      return await getDailySummary(id);
    } catch (err) {
      error.set(messageFor(err, 'Failed to load recap detail'));
      return null;
    }
  };

  return {
    recaps,
    loading,
    error,
    hasMore,
    ensureLoaded,
    loadMore,
    refresh,
    removeRecap,
    generateForDate,
    getRecapDetail,
  };
}

export function useRecaps(options: UseRecapsOptions = {}): UseRecapsReturn {
  const { limit = 30 } = options;
  const store = useMemo(() => createRecapsStore(limit), [limit]);

  useEffect(() => {
    void store.ensureLoaded();
  }, [store]);

  const recaps = useSignalValue(store.recaps);
  const loading = useSignalValue(store.loading);
  const error = useSignalValue(store.error);
  const hasMore = useSignalValue(store.hasMore);
  const groupedRecaps = useMemo(() => groupRecapsByMonth(recaps), [recaps]);

  return {
    recaps,
    groupedRecaps,
    loading,
    error,
    hasMore,
    loadMore: useCallback(() => store.loadMore(), [store]),
    refresh: useCallback(() => store.refresh(), [store]),
    removeRecap: useCallback((id: string) => store.removeRecap(id), [store]),
    generateForDate: useCallback((date: string) => store.generateForDate(date), [store]),
    getRecapDetail: useCallback((id: string) => store.getRecapDetail(id), [store]),
  };
}
