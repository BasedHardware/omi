import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useGoals } from '@/hooks/useGoals';
import type { Goal } from '@/types/goals';

vi.mock('@/lib/api', () => ({
  getGoals: vi.fn(),
  createGoal: vi.fn(),
  updateGoal: vi.fn(),
  updateGoalProgress: vi.fn(),
  deleteGoal: vi.fn(),
}));

const api = await import('@/lib/api');

function goal(overrides: Partial<Goal> = {}): Goal {
  return {
    id: 'goal-1',
    goal_id: 'goal-1',
    title: 'Read books',
    desired_outcome: 'Read books',
    status: 'background',
    source: 'user',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    goal_type: 'numeric',
    current_value: 3,
    target_value: 10,
    min_value: 0,
    max_value: 10,
    is_active: true,
    ...overrides,
  };
}

async function renderLoaded(initial: Goal[] = [goal()]) {
  vi.mocked(api.getGoals).mockResolvedValue(initial);
  const view = renderHook(() => useGoals());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useGoals', () => {
  it('loads goals on mount', async () => {
    const { result } = await renderLoaded();

    expect(result.current.goals).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('surfaces a load failure instead of hanging in a loading state', async () => {
    vi.mocked(api.getGoals).mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useGoals());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('network down');
    expect(result.current.goals).toEqual([]);
  });

  it('appends a created goal without refetching the list', async () => {
    const { result } = await renderLoaded([]);
    vi.mocked(api.createGoal).mockResolvedValue(goal({ id: 'new-goal' }));

    await act(async () => {
      await result.current.addGoal({
        title: 'Read books',
        target_value: 10,
      });
    });

    expect(result.current.goals.map((entry) => entry.id)).toEqual(['new-goal']);
    expect(api.getGoals).toHaveBeenCalledTimes(1);
  });

  it('reports a failed create and leaves the list untouched', async () => {
    const { result } = await renderLoaded([]);
    vi.mocked(api.createGoal).mockRejectedValue(new Error('rejected'));

    let created: Goal | null = goal();
    await act(async () => {
      created = await result.current.addGoal({
        title: 'Read books',
        target_value: 10,
      });
    });

    expect(created).toBeNull();
    expect(result.current.goals).toEqual([]);
    expect(result.current.error).toBe('rejected');
  });

  it('shows the new progress value before the server confirms it', async () => {
    const { result } = await renderLoaded();
    let resolveRequest: ((value: Goal) => void) | undefined;
    vi.mocked(api.updateGoalProgress).mockReturnValue(
      new Promise<Goal>((resolve) => {
        resolveRequest = resolve;
      }),
    );

    act(() => {
      void result.current.setProgress('goal-1', 7);
    });

    expect(result.current.goals[0].current_value).toBe(7);

    await act(async () => {
      resolveRequest?.(goal({ current_value: 7 }));
    });

    expect(result.current.goals[0].current_value).toBe(7);
  });

  it('rolls the progress value back when the server rejects the write', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.updateGoalProgress).mockRejectedValue(new Error('conflict'));

    let succeeded = true;
    await act(async () => {
      succeeded = await result.current.setProgress('goal-1', 7);
    });

    expect(succeeded).toBe(false);
    expect(result.current.goals[0].current_value).toBe(3);
    expect(result.current.error).toBe('conflict');
  });

  it('serializes overlapping writes for the same goal', async () => {
    const { result } = await renderLoaded();
    let resolveRename: ((value: Goal) => void) | undefined;
    let resolveProgress: ((value: Goal) => void) | undefined;
    vi.mocked(api.updateGoal).mockReturnValue(
      new Promise<Goal>((resolve) => {
        resolveRename = resolve;
      }),
    );
    vi.mocked(api.updateGoalProgress).mockReturnValue(
      new Promise<Goal>((resolve) => {
        resolveProgress = resolve;
      }),
    );

    let renamePromise: Promise<boolean>;
    let progressPromise: Promise<boolean>;
    act(() => {
      renamePromise = result.current.editGoal('goal-1', { title: 'Read more books' });
      progressPromise = result.current.setProgress('goal-1', 7);
    });

    expect(result.current.goals[0].title).toBe('Read more books');
    expect(api.updateGoal).toHaveBeenCalledOnce();
    expect(api.updateGoalProgress).not.toHaveBeenCalled();

    await act(async () => {
      resolveRename?.(goal({ title: 'Read more books' }));
      await renamePromise!;
    });

    await waitFor(() => expect(api.updateGoalProgress).toHaveBeenCalledOnce());
    expect(result.current.goals[0]).toEqual(
      expect.objectContaining({ title: 'Read more books', current_value: 7 }),
    );

    await act(async () => {
      resolveProgress?.(goal({ title: 'Read more books', current_value: 7 }));
      await progressPromise!;
    });

    expect(result.current.goals[0]).toEqual(
      expect.objectContaining({ title: 'Read more books', current_value: 7 }),
    );
  });

  it('does not let a failed earlier write roll back a later write', async () => {
    const { result } = await renderLoaded();
    let rejectRename: ((reason: Error) => void) | undefined;
    let resolveProgress: ((value: Goal) => void) | undefined;
    vi.mocked(api.updateGoal).mockReturnValue(
      new Promise<Goal>((_resolve, reject) => {
        rejectRename = reject;
      }),
    );
    vi.mocked(api.updateGoalProgress).mockReturnValue(
      new Promise<Goal>((resolve) => {
        resolveProgress = resolve;
      }),
    );

    let renamePromise: Promise<boolean>;
    let progressPromise: Promise<boolean>;
    act(() => {
      renamePromise = result.current.editGoal('goal-1', { title: 'Read more books' });
      progressPromise = result.current.setProgress('goal-1', 7);
    });

    await act(async () => {
      rejectRename?.(new Error('rename conflict'));
      expect(await renamePromise!).toBe(false);
    });

    await waitFor(() => expect(api.updateGoalProgress).toHaveBeenCalledOnce());
    expect(result.current.goals[0]).toEqual(
      expect.objectContaining({ title: 'Read books', current_value: 7 }),
    );
    expect(result.current.error).toBe('rename conflict');

    await act(async () => {
      resolveProgress?.(goal({ current_value: 7 }));
      expect(await progressPromise!).toBe(true);
    });

    expect(result.current.goals[0]).toEqual(
      expect.objectContaining({ title: 'Read books', current_value: 7 }),
    );
  });

  it('restores a deleted goal when the delete fails', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.deleteGoal).mockRejectedValue(new Error('offline'));

    let succeeded = true;
    await act(async () => {
      succeeded = await result.current.removeGoal('goal-1');
    });

    expect(succeeded).toBe(false);
    expect(result.current.goals.map((entry) => entry.id)).toEqual(['goal-1']);
    expect(result.current.error).toBe('offline');
  });

  it('keeps a goal removed when the delete succeeds', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.deleteGoal).mockResolvedValue(undefined);

    await act(async () => {
      await result.current.removeGoal('goal-1');
    });

    expect(result.current.goals).toEqual([]);
    expect(result.current.error).toBeNull();
  });
});
