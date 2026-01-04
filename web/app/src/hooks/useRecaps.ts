'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import type { DailySummary, GroupedDailySummaries } from '@/types/recap';
import {
  getDailySummaries,
  getDailySummary,
  deleteDailySummary,
  generateTestDailySummary,
} from '@/lib/api';

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

// Module-level cache that persists across component mounts
interface CacheEntry {
  recaps: DailySummary[];
  offset: number;
  hasMore: boolean;
  timestamp: number;
}

let recapCache: CacheEntry | null = null;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function getFromCache(): CacheEntry | null {
  return recapCache;
}

function setToCache(recaps: DailySummary[], offset: number, hasMore: boolean): void {
  recapCache = {
    recaps,
    offset,
    hasMore,
    timestamp: Date.now(),
  };
}

function updateCacheRecaps(updater: (recaps: DailySummary[]) => DailySummary[]): void {
  if (recapCache) {
    recapCache.recaps = updater(recapCache.recaps);
  }
}

function isCacheStale(entry: CacheEntry): boolean {
  return Date.now() - entry.timestamp > CACHE_TTL;
}

// Parse YYYY-MM-DD as local date (not UTC)
function parseLocalDate(dateString: string): Date {
  const [year, month, day] = dateString.split('-').map(Number);
  return new Date(year, month - 1, day);
}

// Group recaps by month (e.g., "January 2025")
function groupByMonth(recaps: DailySummary[]): GroupedDailySummaries {
  if (!Array.isArray(recaps) || recaps.length === 0) {
    return {};
  }
  return recaps.reduce((groups, recap) => {
    const date = parseLocalDate(recap.date);
    const monthKey = date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
    });
    if (!groups[monthKey]) {
      groups[monthKey] = [];
    }
    groups[monthKey].push(recap);
    return groups;
  }, {} as GroupedDailySummaries);
}

// Safely extract array from API response
function normalizeRecapsResponse(response: unknown): DailySummary[] {
  if (Array.isArray(response)) {
    return response;
  }
  // Handle wrapped response like { daily_summaries: [...] }
  if (response && typeof response === 'object') {
    const obj = response as Record<string, unknown>;
    if (Array.isArray(obj.daily_summaries)) {
      return obj.daily_summaries;
    }
    if (Array.isArray(obj.summaries)) {
      return obj.summaries;
    }
    if (Array.isArray(obj.data)) {
      return obj.data;
    }
  }
  return [];
}

export function useRecaps(options: UseRecapsOptions = {}): UseRecapsReturn {
  const { limit = 30 } = options;

  const cachedEntry = getFromCache();

  // Initialize state from cache if available
  const [recaps, setRecaps] = useState<DailySummary[]>(cachedEntry?.recaps || []);
  const [loading, setLoading] = useState(!cachedEntry);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(cachedEntry?.hasMore ?? true);

  // Use ref for offset to avoid dependency issues
  const offsetRef = useRef(cachedEntry?.offset || 0);
  // Track if a fetch is in progress to prevent concurrent fetches
  const fetchingRef = useRef(false);
  // Track if initial fetch is done
  const initializedRef = useRef(false);

  // Compute grouped recaps
  const groupedRecaps = useMemo(() => groupByMonth(recaps), [recaps]);

  // Core fetch function
  const doFetch = useCallback(async (currentOffset: number): Promise<DailySummary[]> => {
    const result = await getDailySummaries({
      limit,
      offset: currentOffset,
    });
    return normalizeRecapsResponse(result);
  }, [limit]);

  // Initial load
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    const cached = getFromCache();

    // If we have fresh cache, use it and skip fetch
    if (cached && !isCacheStale(cached)) {
      setRecaps(cached.recaps);
      setHasMore(cached.hasMore);
      offsetRef.current = cached.offset;
      setLoading(false);
      return;
    }

    // If we have stale cache, show it but refresh in background
    if (cached) {
      setRecaps(cached.recaps);
      setHasMore(cached.hasMore);
      offsetRef.current = cached.offset;
      setLoading(false);
    }

    const loadInitial = async () => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;

      if (!cached) {
        setLoading(true);
      }
      setError(null);

      try {
        const result = await doFetch(0);
        setRecaps(result);
        offsetRef.current = result.length;
        setHasMore(result.length >= limit);
        setToCache(result, result.length, result.length >= limit);
      } catch (err) {
        if (!cached) {
          setError(err instanceof Error ? err.message : 'Failed to load recaps');
        }
      } finally {
        setLoading(false);
        fetchingRef.current = false;
      }
    };

    loadInitial();
  }, [doFetch, limit]);

  // Load more (pagination)
  const loadMore = useCallback(async () => {
    if (fetchingRef.current || !hasMore) return;
    fetchingRef.current = true;
    setLoading(true);

    try {
      const result = await doFetch(offsetRef.current);

      setRecaps((prev) => {
        // Deduplicate
        const existingIds = new Set(prev.map((r) => r.id));
        const newRecaps = result.filter((r) => !existingIds.has(r.id));
        const updated = [...prev, ...newRecaps];
        const newOffset = offsetRef.current + result.length;
        const newHasMore = result.length >= limit;
        setToCache(updated, newOffset, newHasMore);
        return updated;
      });

      offsetRef.current += result.length;
      setHasMore(result.length >= limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more recaps');
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [doFetch, hasMore, limit]);

  // Refresh
  const refresh = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setLoading(true);
    setError(null);

    try {
      const result = await doFetch(0);
      setRecaps(result);
      offsetRef.current = result.length;
      setHasMore(result.length >= limit);
      setToCache(result, result.length, result.length >= limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh recaps');
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [doFetch, limit]);

  // Remove recap
  const removeRecap = useCallback(async (id: string): Promise<boolean> => {
    try {
      await deleteDailySummary(id);
      const updater = (prev: DailySummary[]) => prev.filter((r) => r.id !== id);
      setRecaps(updater);
      updateCacheRecaps(updater);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete recap');
      return false;
    }
  }, []);

  // Generate recap for a specific date
  const generateForDate = useCallback(async (date: string): Promise<DailySummary | null> => {
    try {
      const newRecap = await generateTestDailySummary(date);
      setRecaps((prev) => {
        // Add to beginning and sort by date descending
        const updated = [newRecap, ...prev.filter((r) => r.id !== newRecap.id)];
        updated.sort((a, b) => parseLocalDate(b.date).getTime() - parseLocalDate(a.date).getTime());
        updateCacheRecaps(() => updated);
        return updated;
      });
      return newRecap;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate recap');
      return null;
    }
  }, []);

  // Get single recap detail
  const getRecapDetail = useCallback(async (id: string): Promise<DailySummary | null> => {
    try {
      return await getDailySummary(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load recap detail');
      return null;
    }
  }, []);

  return {
    recaps,
    groupedRecaps,
    loading,
    error,
    hasMore,
    loadMore,
    refresh,
    removeRecap,
    generateForDate,
    getRecapDetail,
  };
}
