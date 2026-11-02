import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActionItem } from '@/types/conversation';

vi.mock('@/lib/api', () => ({
  getActionItems: vi.fn(),
  createActionItem: vi.fn(),
  toggleActionItemCompleted: vi.fn(),
  updateActionItemDueDate: vi.fn(),
  updateActionItemDescription: vi.fn(),
  deleteActionItem: vi.fn(),
}));

const { getActionItems, toggleActionItemCompleted } = await import('@/lib/api');
const { useActionItems } = await import('@/hooks/useActionItems');

function task(id: string, completedAt: string | null): ActionItem {
  return {
    id,
    description: id,
    completed: completedAt !== null,
    completed_at: completedAt,
    created_at: '2026-01-01T00:00:00Z',
  };
}

async function renderLoaded(items: ActionItem[]) {
  vi.mocked(getActionItems).mockResolvedValue({ items, hasMore: false });
  const view = renderHook(() => useActionItems());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useActionItems toggleComplete', () => {
  it('keeps the completion date of a task that fails to reopen', async () => {
    const { result } = await renderLoaded([
      task('call-mom', '2026-10-15T18:00:00.000Z'),
      task('buy-milk', '2026-10-10T09:00:00.000Z'),
    ]);
    vi.mocked(toggleActionItemCompleted).mockRejectedValue(new Error('network down'));

    await act(async () => {
      await result.current.toggleComplete('call-mom', false);
    });

    expect(toggleActionItemCompleted).toHaveBeenCalledWith('call-mom', false);
    expect(result.current.error).toBe('network down');
    // The server still has the task completed on Oct 15, so its row shows that
    // date again and it stays first in the Completed list (most recent first).
    expect(result.current.items.find((t) => t.id === 'call-mom')).toMatchObject({
      completed: true,
      completed_at: '2026-10-15T18:00:00.000Z',
    });
    expect(result.current.sortedFlatList.completed.map((t) => t.id)).toEqual([
      'call-mom',
      'buy-milk',
    ]);
  });

  it('shows a task that fails to complete as open again', async () => {
    const { result } = await renderLoaded([task('buy-milk', null)]);
    vi.mocked(toggleActionItemCompleted).mockRejectedValue(new Error('network down'));

    await act(async () => {
      await result.current.toggleComplete('buy-milk', true);
    });

    expect(toggleActionItemCompleted).toHaveBeenCalledWith('buy-milk', true);
    expect(result.current.items).toEqual([task('buy-milk', null)]);
    expect(result.current.sortedFlatList.pending.map((t) => t.id)).toEqual(['buy-milk']);
    expect(result.current.error).toBe('network down');
  });
});
