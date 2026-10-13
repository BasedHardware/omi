import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useRecaps } from '../useRecaps';
import type { DailySummary } from '@/types/recap';

const api = vi.hoisted(() => ({ create: vi.fn(), list: vi.fn() }));
vi.mock('@/lib/api', () => ({
  createDailySummary: api.create,
  getDailySummaries: api.list,
  getDailySummary: vi.fn(),
  deleteDailySummary: vi.fn(),
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
    api.list.mockResolvedValue([]);
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
});
