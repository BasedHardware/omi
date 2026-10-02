import React from 'react';
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoriesPrefetcher } from '../MemoriesPrefetcher';

const mocks = vi.hoisted(() => ({
  authUser: { uid: 'owner-a' } as { uid: string } | null,
  authLoading: false,
  backendScope: 'https://backend-a',
  getMemories: vi.fn(),
  isCacheFresh: vi.fn(),
  cacheMemories: vi.fn(),
}));

vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({ user: mocks.authUser, loading: mocks.authLoading }),
}));

vi.mock('@/lib/api', () => ({
  getMemories: mocks.getMemories,
}));

vi.mock('@/lib/indexeddb', () => ({
  isCacheFresh: mocks.isCacheFresh,
  cacheMemories: mocks.cacheMemories,
}));

vi.mock('@/lib/cache', () => ({
  getMemoryBackendScope: () => mocks.backendScope,
  memoryCacheScopeKey: (scope: { ownerId: string; backendScope: string }) =>
    `${scope.ownerId}|${scope.backendScope}`,
}));

describe('MemoriesPrefetcher', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.authUser = { uid: 'owner-a' };
    mocks.authLoading = false;
    mocks.backendScope = 'https://backend-a';
    mocks.isCacheFresh.mockReset();
    mocks.isCacheFresh.mockResolvedValue(false);
    mocks.getMemories.mockReset();
    mocks.getMemories.mockResolvedValue([]);
    mocks.cacheMemories.mockReset();
    mocks.cacheMemories.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('prefetches after rerenders that recreate the scope object before the timer fires', async () => {
    mocks.getMemories.mockResolvedValue([{ id: 'memory-owner-a' }]);

    const { rerender } = render(<MemoriesPrefetcher />);
    // Unrelated rerenders recreate `scope`; the stable scopeKey must keep the
    // scheduled prefetch alive instead of clearing the timer and skipping it.
    rerender(<MemoriesPrefetcher />);
    rerender(<MemoriesPrefetcher />);
    expect(mocks.getMemories).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(mocks.getMemories).toHaveBeenCalledTimes(1);
    expect(mocks.cacheMemories).toHaveBeenCalledWith(
      [{ id: 'memory-owner-a' }],
      'useful_now',
      { ownerId: 'owner-a', backendScope: 'https://backend-a' },
    );
  });

  it('does not cache the previous owner response when the owner changes mid-flight', async () => {
    let resolveFetch!: (memories: unknown[]) => void;
    const pendingFetch = new Promise<unknown[]>((resolve) => {
      resolveFetch = resolve;
    });
    mocks.getMemories
      .mockReturnValueOnce(pendingFetch)
      .mockResolvedValue([{ id: 'memory-owner-b' }]);

    const { rerender } = render(<MemoriesPrefetcher />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    // Owner A's prefetch request is now pending.
    expect(mocks.getMemories).toHaveBeenCalledTimes(1);

    act(() => {
      mocks.authUser = { uid: 'owner-b' };
      rerender(<MemoriesPrefetcher />);
    });

    resolveFetch([{ id: 'memory-owner-a' }]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Only owner B's own prefetch may write; A's late response is discarded
    // before it can be cached under A's (or B's) scope.
    const scopesWritten = mocks.cacheMemories.mock.calls.map((call) => call[2]);
    expect(scopesWritten).toEqual([
      { ownerId: 'owner-b', backendScope: 'https://backend-a' },
    ]);
  });
});
