import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActionItem } from '@/types/conversation';

vi.mock('@/lib/cache', () => ({
  onCacheInvalidation: vi.fn(() => () => {}),
  invalidationPatterns: { actionItems: 'actionItems' },
}));

vi.mock('@/features/tasks/api', () => ({
  getActionItems: vi.fn(),
  createActionItem: vi.fn(),
  toggleActionItemCompleted: vi.fn(),
  updateActionItemDueDate: vi.fn(),
  updateActionItemDescription: vi.fn(),
  deleteActionItem: vi.fn(),
}));

const api = await import('@/features/tasks/api');
const { useActionItems } = await import('@/features/tasks/useActionItems');

function item(overrides: Partial<ActionItem> = {}): ActionItem {
  return {
    id: 'task-1',
    description: 'Review the launch plan',
    completed: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

async function renderLoaded(initial: ActionItem[] = [item()]) {
  vi.mocked(api.getActionItems).mockResolvedValue({ items: initial, hasMore: false } as never);
  const view = renderHook(() => useActionItems());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useActionItems', () => {
  it('loads tasks on mount', async () => {
    const { result } = await renderLoaded();

    expect(result.current.items).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('shows the completed flag before the server confirms it', async () => {
    const { result } = await renderLoaded();
    let resolveRequest: (() => void) | undefined;
    vi.mocked(api.toggleActionItemCompleted).mockReturnValue(
      new Promise<void>((resolve) => {
        resolveRequest = resolve;
      }),
    );

    act(() => {
      void result.current.toggleComplete('task-1', true);
    });

    expect(result.current.items[0].completed).toBe(true);

    await act(async () => {
      resolveRequest?.();
    });
  });

  it('rolls a failed complete back using the committed row', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.toggleActionItemCompleted).mockRejectedValue(new Error('conflict'));

    await act(async () => {
      await result.current.toggleComplete('task-1', true);
    });

    expect(result.current.items[0].completed).toBe(false);
    expect(result.current.error).toBe('conflict');
  });

  it('restores a deleted task when the delete fails', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.deleteActionItem).mockRejectedValue(new Error('offline'));

    await act(async () => {
      await result.current.removeItem('task-1');
    });

    expect(result.current.items.map((entry) => entry.id)).toEqual(['task-1']);
    expect(result.current.error).toBe('offline');
  });
});
