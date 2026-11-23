import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useActivityFailures } from '../useActivityFailures';
import type { Conversation } from '@/types/conversation';

const failed = {
  id: 'hidden',
  status: 'processing',
  home_step: 'failed',
} as Conversation;
const empty: Conversation[] = [];
describe('Activity reachability across Home filters', () => {
  it('retains loaded and search-only failures across filters and removes completions', async () => {
    const { result, rerender } = renderHook(
      ({ home, search }) => useActivityFailures(home, search, 'owner'),
      { initialProps: { home: [failed], search: [{ ...failed, id: 'search-only' }] } },
    );
    await waitFor(() => expect(result.current.failures).toHaveLength(2));
    rerender({ home: [], search: [] });
    expect(result.current.failures.map((row) => row.id)).toEqual([
      'hidden',
      'search-only',
    ]);
    rerender({
      home: [{ ...failed, home_step: 'done', status: 'completed' }],
      search: [],
    });
    await waitFor(() =>
      expect(result.current.failures.map((row) => row.id)).toEqual(['search-only']),
    );
    act(() => result.current.forget(['search-only']));
    rerender({ home: [], search: [{ ...failed, id: 'search-only' }] });
    expect(result.current.failures).toEqual([]);
  });
  it('resolves an off-page retry without resurrecting its old search snapshot', async () => {
    const hits = [failed];
    const { result, rerender } = renderHook(
      ({ home, search }) => useActivityFailures(home, search, 'owner'),
      { initialProps: { home: empty, search: hits } },
    );
    await waitFor(() => expect(result.current.failures).toEqual(hits));
    rerender({ home: empty, search: empty });
    act(() => result.current.resolveRetry(failed.id));
    expect(result.current.failures).toEqual([]);
    rerender({ home: [], search: hits });
    expect(result.current.failures).toEqual([]);
    // A later authoritative failure is still reachable; retry is not deletion.
    const nextAttempt = { ...failed };
    rerender({ home: [nextAttempt], search: empty });
    await waitFor(() => expect(result.current.failures).toEqual([nextAttempt]));
  });
  it('clears at an account switch without remembering the previous account arrays again', async () => {
    const old = [failed];
    const { result, rerender } = renderHook(
      ({ owner, home }) => useActivityFailures(home, empty, owner),
      { initialProps: { owner: 'first', home: old } },
    );
    await waitFor(() => expect(result.current.failures).toHaveLength(1));
    rerender({ owner: 'second', home: old });
    expect(result.current.failures).toEqual([]);
    rerender({ owner: 'second', home: [{ ...failed, id: 'second-owner' }] });
    await waitFor(() =>
      expect(result.current.failures.map((row) => row.id)).toEqual(['second-owner']),
    );
  });
});
