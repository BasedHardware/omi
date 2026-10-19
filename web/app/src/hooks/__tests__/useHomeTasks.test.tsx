import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  getActionItems: vi.fn(),
  toggleActionItemCompleted: vi.fn().mockResolvedValue(undefined),
}));

const { getActionItems, toggleActionItemCompleted } = await import('@/lib/api');
const { useHomeTasks } = await import('@/hooks/useHomeTasks');

function item(id: string, completed: boolean | null | undefined) {
  return { id, description: id, completed, created_at: '2026-01-01T00:00:00Z' };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useHomeTasks', () => {
  it('shows legacy open tasks whose completed field is missing or null', async () => {
    vi.mocked(getActionItems).mockResolvedValue({
      items: [
        item('open', false),
        item('legacy-null', null),
        item('legacy-missing', undefined),
        item('done', true),
      ],
      hasMore: false,
    } as never);

    const { result } = renderHook(() => useHomeTasks());

    await waitFor(() => expect(result.current.items.length).toBeGreaterThan(0));

    // The equality filter the server applies to `completed=false` drops legacy
    // documents; the hub must list them like every other surface does.
    expect(getActionItems).toHaveBeenCalledWith(
      expect.not.objectContaining({ completed: expect.anything() }),
    );
    expect(result.current.items.map((task) => task.id)).toEqual([
      'open',
      'legacy-null',
      'legacy-missing',
    ]);
  });

  it('puts a task back and says why when completing it fails', async () => {
    vi.mocked(getActionItems).mockResolvedValue({
      items: [item('first', false), item('second', false)],
      hasMore: false,
    } as never);
    vi.mocked(toggleActionItemCompleted).mockRejectedValueOnce(
      new Error('API error: 500 Internal Server Error'),
    );

    const { result } = renderHook(() => useHomeTasks());

    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(result.current.completeError).toBeNull();

    await act(async () => {
      await result.current.complete('first');
    });

    // The row comes back, so the hub has to say the tick did not save rather
    // than let the task look done and then reappear.
    expect(toggleActionItemCompleted).toHaveBeenCalledWith('first', true);
    expect(result.current.items.map((task) => task.id)).toEqual(['first', 'second']);
    expect(result.current.completeError).toBe('API error: 500 Internal Server Error');

    // A later tick that saves clears the message along with its row.
    await act(async () => {
      await result.current.complete('second');
    });

    expect(result.current.items.map((task) => task.id)).toEqual(['first']);
    expect(result.current.completeError).toBeNull();
  });
});
