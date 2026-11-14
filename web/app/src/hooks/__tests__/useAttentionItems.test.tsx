import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAttentionItems } from '../useAttentionItems';
import { getAttentionItems, retryAttentionItem } from '@/lib/api';
import type { AttentionItem } from '@/lib/attentionItems';
vi.mock('@/lib/api', () => ({ getAttentionItems: vi.fn(), retryAttentionItem: vi.fn() }));
const notes = {
  id: 'notes',
  kind: 'conversation_notes_failed_with_outputs',
  conversation_id: 'c',
  retryable: true,
  retry: { state: 'none', operation_id: null },
} as AttentionItem;
const unknown = { ...notes, id: 'future', kind: 'future', conversation_id: 'future' };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getAttentionItems).mockResolvedValue({ items: [notes, unknown] });
  vi.mocked(retryAttentionItem).mockResolvedValue({
    operation_id: 'op',
    state: 'in_progress',
  });
});
describe('server notes attention', () => {
  it('dedupes conversation rows and suppresses stale ledger/projected failures after retry', async () => {
    vi.mocked(getAttentionItems).mockResolvedValue({
      items: [
        { ...notes, id: 'summary', kind: 'conversation_summary_failed' },
        notes,
        unknown,
      ],
    });
    const { result } = renderHook(() => useAttentionItems(true, 'owner'));
    await waitFor(() =>
      expect(result.current.items.map((i) => i.id)).toEqual(['notes', 'future']),
    );
    await act(async () => result.current.retry(unknown));
    expect(retryAttentionItem).not.toHaveBeenCalled();
    await act(async () => result.current.retry(notes));
    expect(retryAttentionItem).toHaveBeenCalledWith('notes', expect.any(String));
    expect(result.current.items).toEqual([unknown]);
    expect(result.current.conversationIds.has('c')).toBe(true);
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });
    expect(result.current.items).toEqual([unknown]);
  });
  it.each([409, 500])(
    'keeps an error row after HTTP %s and reuses its ambiguous key',
    async (status) => {
      vi.mocked(retryAttentionItem).mockRejectedValueOnce(
        Object.assign(new Error('rejected'), { status }),
      );
      const { result } = renderHook(() => useAttentionItems(true, 'owner'));
      await waitFor(() => expect(result.current.items).toHaveLength(2));
      await act(async () => result.current.retry(notes));
      expect(result.current.items).toContainEqual(notes);
      expect(result.current.errors.has('notes')).toBe(true);
      expect(result.current.retrying.size).toBe(0);
      const key = vi.mocked(retryAttentionItem).mock.calls[0][1];
      await act(async () => result.current.retry(notes));
      expect(retryAttentionItem).toHaveBeenLastCalledWith('notes', key);
      expect(result.current.items).toEqual([unknown]);
    },
  );
  it.each(['in_progress', 'succeeded', 'not_retryable', 'transport', 'failed'])(
    'reconciles remembered notes failure only for an authoritative %s result',
    async (state) => {
      const resolved = vi.fn();
      if (state === 'not_retryable')
        vi.mocked(retryAttentionItem).mockRejectedValueOnce(
          Object.assign(new Error('terminal'), { status: 409, state }),
        );
      else if (state === 'transport')
        vi.mocked(retryAttentionItem).mockRejectedValueOnce(new Error('offline'));
      else
        vi.mocked(retryAttentionItem).mockResolvedValueOnce({
          operation_id: 'op',
          state,
        });
      const { result } = renderHook(() => useAttentionItems(true, 'owner', resolved));
      await waitFor(() => expect(result.current.items).toHaveLength(2));
      await act(async () => result.current.retry(notes));
      if (['in_progress', 'succeeded', 'not_retryable'].includes(state)) {
        expect(resolved).toHaveBeenCalledExactlyOnceWith(notes.conversation_id);
      } else expect(resolved).not.toHaveBeenCalled();
      if (['not_retryable', 'transport', 'failed'].includes(state)) {
        expect(result.current.items).toContainEqual(notes);
        expect(result.current.errors.has(notes.id)).toBe(true);
      }
    },
  );
  it('does not treat a failed operation response as success', async () => {
    vi.mocked(retryAttentionItem).mockResolvedValueOnce({
      operation_id: 'op',
      state: 'failed',
    });
    const { result } = renderHook(() => useAttentionItems(true, 'owner'));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    await act(async () => result.current.retry(notes));
    expect(result.current.items).toContainEqual(notes);
    expect(result.current.errors.has('notes')).toBe(true);
  });
  it('ignores a pre-retry read and fences double taps', async () => {
    const { result } = renderHook(() => useAttentionItems(true, 'owner'));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    let finishRead!: (value: { items: AttentionItem[] }) => void;
    vi.mocked(getAttentionItems).mockReturnValueOnce(
      new Promise((resolve) => {
        finishRead = resolve;
      }),
    );
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    let finishRetry!: (value: { operation_id: string; state: string }) => void;
    vi.mocked(retryAttentionItem).mockReturnValueOnce(
      new Promise((resolve) => {
        finishRetry = resolve;
      }),
    );
    let retry!: Promise<void>;
    act(() => {
      retry = result.current.retry(notes);
    });
    await act(async () => result.current.retry(notes));
    expect(retryAttentionItem).toHaveBeenCalledOnce();
    await act(async () => {
      finishRetry({ operation_id: 'op', state: 'succeeded' });
      await retry;
    });
    await act(async () => {
      finishRead({ items: [notes] });
    });
    expect(result.current.items).toEqual([unknown]);
  });
  it('allows a fresh notes generation after an earlier accepted retry', async () => {
    const { result } = renderHook(() => useAttentionItems(true, 'owner'));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    await act(async () => result.current.retry(notes));
    const fresh = { ...notes, id: 'new-generation' };
    vi.mocked(getAttentionItems).mockResolvedValueOnce({ items: [fresh] });
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });
    expect(result.current.items).toEqual([fresh]);
  });
  it('switch off clears the new surface and account reset rejects late retries', async () => {
    const { result, rerender } = renderHook(
      ({ enabled, owner }) => useAttentionItems(enabled, owner),
      {
        initialProps: { enabled: true, owner: 'first' },
      },
    );
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    let finish!: (value: { operation_id: string; state: string }) => void;
    vi.mocked(retryAttentionItem).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.retry(notes);
    });
    rerender({ enabled: false, owner: 'second' });
    await act(async () => {
      finish({ operation_id: 'op', state: 'succeeded' });
      await pending;
    });
    expect(result.current.items).toEqual([]);
    expect(result.current.conversationIds.size).toBe(0);
    expect(result.current.errors.size).toBe(0);
  });
});
