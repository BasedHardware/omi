import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { invalidateCache, invalidationPatterns } from '@/lib/cache';

vi.mock('@/lib/api', () => ({
  getActionItems: vi.fn(),
  createActionItem: vi.fn(),
  toggleActionItemCompleted: vi.fn(),
  updateActionItemDueDate: vi.fn(),
  updateActionItemDescription: vi.fn(),
  deleteActionItem: vi.fn(),
}));

const { getActionItems } = await import('@/lib/api');
const { useActionItems } = await import('@/hooks/useActionItems');

function item(id: string) {
  return { id, description: id, completed: false, created_at: '2026-01-01T00:00:00Z' };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useActionItems', () => {
  it('keeps the loaded list visible while a cache-invalidation refetch is in flight', async () => {
    let resolveRefresh: (value: {
      items: ReturnType<typeof item>[];
      hasMore: boolean;
    }) => void = () => undefined;

    vi.mocked(getActionItems)
      .mockResolvedValueOnce({ items: [item('a'), item('b')], hasMore: false } as never)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          }),
      );

    const { result } = renderHook(() => useActionItems());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items.map((task) => task.id)).toEqual(['a', 'b']);

    act(() => {
      invalidateCache(invalidationPatterns.actionItems);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.items.map((task) => task.id)).toEqual(['a', 'b']);

    await act(async () => {
      resolveRefresh({ items: [item('a')], hasMore: false });
    });

    await waitFor(() =>
      expect(result.current.items.map((task) => task.id)).toEqual(['a']),
    );
    expect(result.current.loading).toBe(false);
  });
});
