import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  getActionItems: vi.fn(),
  toggleActionItemCompleted: vi.fn().mockResolvedValue(undefined),
}));

const { getActionItems } = await import('@/lib/api');
const { useHomeTasks } = await import('@/hooks/useHomeTasks');

function item(id: string, completed: boolean | null | undefined) {
  return { id, description: id, completed, created_at: '2026-01-01T00:00:00Z' };
}

beforeEach(() => {
  vi.clearAllMocks();
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
});
