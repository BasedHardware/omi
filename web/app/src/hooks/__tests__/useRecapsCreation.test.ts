import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useRecaps } from '../useRecaps';
import type { DailySummary } from '@/types/recap';

const api = vi.hoisted(() => ({ create: vi.fn(), list: vi.fn(), delete: vi.fn() }));
vi.mock('@/lib/api', () => ({
  createDailySummary: api.create,
  getDailySummaries: api.list,
  getDailySummary: vi.fn(),
  deleteDailySummary: api.delete,
}));
vi.mock('@/lib/cache', () => ({
  getCache: vi.fn().mockReturnValue(null),
  setCache: vi.fn(),
  updateCache: vi.fn(),
  CACHE_TTL: { MEDIUM: 1 },
}));
const recap = { id: 'r', date: '2026-10-04', headline: 'Recovered day' } as DailySummary;

describe('recap creation in the existing store', () => {
  beforeEach(() => {
    api.list.mockReset().mockResolvedValue([]);
    api.delete.mockReset().mockResolvedValue(undefined);
    api.create.mockReset();
  });
  it('publishes one stable recap when the server returns the same date again', async () => {
    api.create.mockResolvedValue(recap);
    const { result } = renderHook(() => useRecaps({ accountId: 'a' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.generateForDate(recap.date);
      await result.current.generateForDate(recap.date);
    });
    expect(result.current.recaps).toEqual([recap]);
  });
  it('does not publish late data after A-to-B-to-A account churn', async () => {
    let complete!: (recap: DailySummary) => void;
    api.create.mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    const { result, rerender } = renderHook(
      ({ owner }) => useRecaps({ accountId: owner }),
      { initialProps: { owner: 'a' } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    let pending!: Promise<DailySummary>;
    act(() => {
      pending = result.current.generateForDate(recap.date);
    });
    const rejected = expect(pending).rejects.toThrow('earlier session');
    rerender({ owner: 'b' });
    rerender({ owner: 'a' });
    await act(async () => {
      complete(recap);
      await rejected;
    });
    expect(result.current.recaps).toEqual([]);
  });
  it('an initial read predating creation cannot erase the recovered row or cache', async () => {
    let complete!: (rows: DailySummary[]) => void;
    api.list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    api.list.mockResolvedValue([recap]);
    api.create.mockResolvedValue(recap);
    const { result } = renderHook(() => useRecaps({ accountId: 'a' }));
    await act(async () => {
      await result.current.generateForDate(recap.date);
    });
    expect(result.current.recaps).toEqual([recap]);
    await act(async () => {
      complete([]);
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.list).toHaveBeenCalledTimes(2);
    expect(result.current.recaps).toEqual([recap]);
  });
  it('a refresh predating deletion cannot resurrect the deleted row', async () => {
    api.list.mockResolvedValue([recap]);
    const { result } = renderHook(() => useRecaps({ accountId: 'a' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    let complete!: (rows: DailySummary[]) => void;
    api.list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    let refresh!: Promise<void>;
    act(() => {
      refresh = result.current.refresh();
    });
    await act(async () => {
      await result.current.removeRecap(recap.id);
    });
    api.list.mockResolvedValue([]);
    await act(async () => {
      complete([recap]);
      await refresh;
    });
    expect(result.current.recaps).toEqual([]);
  });
  it('late initial reads and details cannot cross account boundaries', async () => {
    let complete!: (rows: DailySummary[]) => void;
    api.list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    const { result, rerender } = renderHook(
      ({ owner }) => useRecaps({ accountId: owner }),
      { initialProps: { owner: 'a' } },
    );
    rerender({ owner: 'b' });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      complete([recap]);
    });
    expect(result.current.recaps).toEqual([]);
  });
  it('malformed list replies remain a retryable read error instead of an empty account', async () => {
    api.list.mockResolvedValue({ invalid: [] });
    const { result } = renderHook(() => useRecaps({ accountId: 'a' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Invalid recap list response');
    api.list.mockResolvedValue([recap]);
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.error).toBeNull();
    expect(result.current.recaps).toEqual([recap]);
  });
  it('a read started during a pending delete cannot adopt the pre-delete snapshot', async () => {
    api.list.mockResolvedValue([recap]);
    const { result } = renderHook(() => useRecaps({ accountId: 'a' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    let finishDelete!: () => void;
    api.delete.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finishDelete = resolve;
        }),
    );
    let deletion!: Promise<boolean>;
    act(() => {
      deletion = result.current.removeRecap(recap.id);
    });
    let finishRead!: (rows: DailySummary[]) => void;
    api.list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishRead = resolve;
        }),
    );
    let refresh!: Promise<void>;
    act(() => {
      refresh = result.current.refresh();
    });
    await act(async () => {
      finishDelete();
      await deletion;
    });
    api.list.mockResolvedValue([]);
    await act(async () => {
      finishRead([recap]);
      await refresh;
    });
    expect(result.current.recaps).toEqual([]);
  });
  it('recovery outside the first page keeps chronological order and server offsets when paging', async () => {
    const days = ['2026-10-12', '2026-10-11', '2026-10-10', '2026-10-09'];
    const saved = days.map((date, index) => ({ ...recap, id: `day-${index}`, date }));
    api.list
      .mockResolvedValueOnce(saved.slice(0, 2))
      .mockResolvedValueOnce(saved.slice(2));
    api.create.mockResolvedValue(recap);
    const { result } = renderHook(() => useRecaps({ accountId: 'a', limit: 2 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.generateForDate(recap.date);
    });
    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.recaps.map((row) => row.date)).toEqual([...days, recap.date]);
    expect(api.list.mock.calls.map(([request]) => request.offset)).toEqual([0, 2]);
  });
});
