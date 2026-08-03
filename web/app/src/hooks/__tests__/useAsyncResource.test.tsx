import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAsyncResource } from '@/hooks/useAsyncResource';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAsyncResource', () => {
  it('loads once and exposes the value', async () => {
    const fetcher = vi.fn().mockResolvedValue('value');
    const { result } = renderHook(() => useAsyncResource('k', fetcher));

    await waitFor(() => expect(result.current.data).toBe('value'));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('does not refetch when the component re-renders with the same key', async () => {
    const fetcher = vi.fn().mockResolvedValue('value');
    const { result, rerender } = renderHook(() => useAsyncResource('k', fetcher));

    await waitFor(() => expect(result.current.data).toBe('value'));
    rerender();
    rerender();

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('refetches when the key changes', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation((): Promise<string> => Promise.resolve('a'));
    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => useAsyncResource(key, fetcher),
      { initialProps: { key: 'first' } },
    );

    await waitFor(() => expect(result.current.data).toBe('a'));

    fetcher.mockResolvedValue('b');
    rerender({ key: 'second' });

    await waitFor(() => expect(result.current.data).toBe('b'));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('does not fetch while the key is null', () => {
    const fetcher = vi.fn().mockResolvedValue('value');
    const { result } = renderHook(() => useAsyncResource(null, fetcher));

    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  it('does not fetch while disabled', () => {
    const fetcher = vi.fn().mockResolvedValue('value');
    renderHook(() => useAsyncResource('k', fetcher, { enabled: false }));

    expect(fetcher).not.toHaveBeenCalled();
  });

  it('surfaces the thrown message', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAsyncResource('k', fetcher));

    await waitFor(() => expect(result.current.error).toBe('boom'));
    expect(result.current.loading).toBe(false);
  });

  it('falls back when the error carries no message', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error(''));
    const { result } = renderHook(() =>
      useAsyncResource('k', fetcher, { fallbackMessage: 'could not load' }),
    );

    await waitFor(() => expect(result.current.error).toBe('could not load'));
  });

  it('clears a previous error on a successful refresh', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAsyncResource('k', fetcher));

    await waitFor(() => expect(result.current.error).toBe('boom'));

    fetcher.mockResolvedValue('value');
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.data).toBe('value');
  });

  it('reads the latest fetcher without needing it memoized', async () => {
    let answer = 'first';
    const { result, rerender } = renderHook(() =>
      // A fresh closure every render, deliberately not wrapped in useCallback.
      useAsyncResource('k', () => Promise.resolve(answer)),
    );

    await waitFor(() => expect(result.current.data).toBe('first'));

    answer = 'second';
    rerender();
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.data).toBe('second');
  });
});
