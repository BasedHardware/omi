'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import type { DailySummary, GroupedDailySummaries } from '@/types/recap';
import {
  getDailySummaries,
  getDailySummary,
  deleteDailySummary,
  createDailySummary,
} from '@/lib/api';
import { getCache, setCache, CACHE_TTL } from '@/lib/cache';

export interface UseRecapsOptions {
  limit?: number;
  accountId?: string;
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
  generateForDate: (date: string) => Promise<DailySummary>;
  getRecapDetail: (id: string) => Promise<DailySummary | null>;
}

// Each authenticated owner has its own recap snapshot.
interface RecapsCacheData {
  recaps: DailySummary[];
  offset: number;
  hasMore: boolean;
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
  throw new Error('Invalid recap list response');
}

export function useRecaps(options: UseRecapsOptions = {}): UseRecapsReturn {
  const { limit = 30, accountId } = options;
  const cacheKey = `recaps:owner=${encodeURIComponent(accountId ?? 'session')}:list`;
  const owner = useRef(accountId);
  const generation = useRef(0);
  if (owner.current !== accountId) generation.current++;
  owner.current = accountId;
  const alive = useRef(true);
  const mutationRevision = useRef(0);
  const activeRead = useRef<symbol | null>(null);
  const cached = getCache<RecapsCacheData>(cacheKey);
  const [snapshot, setSnapshot] = useState({
    generation: generation.current,
    recaps: cached?.data.recaps ?? [],
  });
  const rows = useRef(snapshot.recaps);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(cached?.data.hasMore ?? true);
  const offset = useRef(cached?.data.offset ?? 0);
  const more = useRef(cached?.data.hasMore ?? true);
  const current = useCallback(
    (admitted: number) => alive.current && generation.current === admitted,
    [],
  );

  const publish = useCallback(
    (recaps: DailySummary[]) => {
      rows.current = recaps;
      setSnapshot({ generation: generation.current, recaps });
      setCache<RecapsCacheData>(
        cacheKey,
        {
          recaps,
          offset: offset.current,
          hasMore: more.current,
        },
        CACHE_TTL.MEDIUM,
      );
    },
    [cacheKey],
  );

  // One owner for initial reads, refreshes and pagination. A read admitted
  // before a successful creation/deletion cannot overwrite that mutation.
  const readPage = useCallback(
    async (append: boolean) => {
      if (activeRead.current || (append && !more.current)) return;
      const admitted = generation.current;
      const lease = Symbol('recap read');
      activeRead.current = lease;
      setLoading(true);
      setError(null);
      const pageOffset = append ? offset.current : 0;
      try {
        while (current(admitted)) {
          const revision = mutationRevision.current;
          const result = normalizeRecapsResponse(
            await getDailySummaries({ limit, offset: pageOffset }),
          );
          if (!current(admitted) || activeRead.current !== lease) return;
          // Re-read after the write, using the server's pagination. The stale
          // response must never erase a recovered row or resurrect a deletion.
          if (revision !== mutationRevision.current) continue;
          const existingIds = new Set(rows.current.map((recap) => recap.id));
          const updated = append
            ? [...rows.current, ...result.filter((recap) => !existingIds.has(recap.id))]
            : result;
          updated.sort((a, b) => b.date.localeCompare(a.date));
          offset.current = pageOffset + result.length;
          more.current = result.length >= limit;
          setHasMore(more.current);
          publish(updated);
          return;
        }
      } catch (err) {
        if (current(admitted))
          setError(err instanceof Error ? err.message : 'Failed to load recaps');
      } finally {
        if (activeRead.current === lease) {
          activeRead.current = null;
          if (current(admitted)) setLoading(false);
        }
      }
    },
    [current, limit, publish],
  );

  useEffect(() => {
    alive.current = true;
    // Retire the previous owner's request without letting its finally block
    // unlock this owner's newer read. No old owner's rows are rendered.
    activeRead.current = null;
    const entry = getCache<RecapsCacheData>(cacheKey);
    rows.current = entry?.data.recaps ?? [];
    offset.current = entry?.data.offset ?? 0;
    more.current = entry?.data.hasMore ?? true;
    setSnapshot({ generation: generation.current, recaps: rows.current });
    setHasMore(more.current);
    setError(null);
    setLoading(!entry);
    if (!entry || entry.isStale) void readPage(false);
    return () => {
      alive.current = false;
    };
  }, [cacheKey, readPage]);

  const loadMore = useCallback(() => readPage(true), [readPage]);
  const refresh = useCallback(() => readPage(false), [readPage]);

  const removeRecap = useCallback(
    async (id: string): Promise<boolean> => {
      const admitted = generation.current;
      try {
        await deleteDailySummary(id);
        if (!current(admitted)) return false;
        mutationRevision.current++;
        publish(rows.current.filter((recap) => recap.id !== id));
        return true;
      } catch (err) {
        if (current(admitted))
          setError(err instanceof Error ? err.message : 'Failed to delete recap');
        return false;
      }
    },
    [current, publish],
  );

  const generateForDate = useCallback(
    async (date: string): Promise<DailySummary> => {
      const admitted = generation.current;
      const recap = await createDailySummary(date);
      if (!current(admitted))
        throw new Error('Recap request belongs to an earlier session');
      mutationRevision.current++;
      const updated = [recap, ...rows.current.filter((row) => row.id !== recap.id)];
      updated.sort((a, b) => b.date.localeCompare(a.date));
      publish(updated);
      return recap;
    },
    [current, publish],
  );

  const getRecapDetail = useCallback(
    async (id: string): Promise<DailySummary | null> => {
      const admitted = generation.current;
      try {
        const recap = await getDailySummary(id);
        return current(admitted) ? recap : null;
      } catch (err) {
        if (current(admitted))
          setError(err instanceof Error ? err.message : 'Failed to load recap detail');
        return null;
      }
    },
    [current],
  );

  const recaps = snapshot.generation === generation.current ? snapshot.recaps : [];
  const groupedRecaps = useMemo(() => groupByMonth(recaps), [recaps]);
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
