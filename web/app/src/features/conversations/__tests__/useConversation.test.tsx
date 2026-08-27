import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Conversation } from '@/types/conversation';

vi.mock('@/features/conversations/api', () => ({
  getConversation: vi.fn(),
}));

const api = await import('@/features/conversations/api');
const { useConversation } = await import('@/features/conversations/useConversation');

function conversation(id: string): Conversation {
  return {
    id,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:00Z',
    structured: { title: id, overview: '', emoji: '', category: 'other' },
  } as unknown as Conversation;
}

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useConversation', () => {
  it('loads a conversation by id', async () => {
    vi.mocked(api.getConversation).mockResolvedValue(conversation('c1'));
    const { result } = renderHook(() => useConversation('c1'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.conversation?.id).toBe('c1');
  });

  it('applies a local update without refetching', async () => {
    vi.mocked(api.getConversation).mockResolvedValue(conversation('c1'));
    const { result } = renderHook(() => useConversation('c1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.update({
        ...conversation('c1'),
        structured: {
          title: 'Renamed',
          overview: '',
          emoji: '',
          category: 'other',
        },
      } as Conversation);
    });

    expect(result.current.conversation?.structured.title).toBe('Renamed');
    expect(api.getConversation).toHaveBeenCalledTimes(1);
  });

  it('does not land a previous id after the selection changes', async () => {
    const first = deferred<Conversation>();
    const second = deferred<Conversation>();
    vi.mocked(api.getConversation)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useConversation(id),
      { initialProps: { id: 'c-a' } },
    );

    rerender({ id: 'c-b' });

    await act(async () => {
      second.resolve(conversation('c-b'));
      await Promise.resolve();
      first.resolve(conversation('c-a'));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.conversation?.id).toBe('c-b'));
  });
});
