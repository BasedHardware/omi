import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  getGoalAdvice: vi.fn(),
  getGoalHistory: vi.fn().mockResolvedValue([]),
}));

const { getGoalAdvice } = await import('@/lib/api');
const { useGoalDetail } = await import('@/hooks/useGoalDetail');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useGoalDetail advice ownership', () => {
  it('drops advice that arrives after the reader switched goals', async () => {
    let resolveFirst!: (value: string) => void;
    vi.mocked(getGoalAdvice).mockReturnValueOnce(
      new Promise<string>((resolve) => {
        resolveFirst = resolve;
      }),
    );

    const { result, rerender } = renderHook(
      ({ goalId }: { goalId: string }) => useGoalDetail(goalId),
      { initialProps: { goalId: 'goal-a' } },
    );

    await act(async () => {
      void result.current.requestAdvice();
    });

    rerender({ goalId: 'goal-b' });

    await act(async () => {
      resolveFirst('advice for goal A');
      await Promise.resolve();
    });

    expect(result.current.advice).toBeNull();
    // The new goal must be askable straight away rather than waiting on a
    // request that was never its own.
    expect(result.current.adviceLoading).toBe(false);
  });
});
