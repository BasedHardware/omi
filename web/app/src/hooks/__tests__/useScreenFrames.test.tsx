import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useScreenFrames } from '@/hooks/useScreenFrames';
import type {
  ConversationScreenFrame,
  ConversationScreenFrameSet,
} from '@/types/conversation';

vi.mock('@/lib/api', () => ({
  getConversationScreenFrames: vi.fn(),
  deleteScreenFrame: vi.fn(),
  deleteAllScreenFrames: vi.fn(),
  patchScreenFrameSharing: vi.fn(),
}));

const api = await import('@/lib/api');

function frame(id: string): ConversationScreenFrame {
  return {
    id,
    captured_at: '2026-08-24T10:00:00Z',
    role: 'strip',
    rank: 0,
    caption: `caption-${id}`,
    labels: [],
    source_badge: null,
    focal_region: null,
    width: 1600,
    height: 900,
    content_url: `https://example.com/${id}.jpg`,
    thumbnail_url: `https://example.com/${id}_thumb.jpg`,
    url_expires_at: '2026-08-24T11:00:00Z',
    ground: { stops: ['#101010', '#202020'], is_neutral: false },
  };
}

function frameSet(
  overrides: Partial<ConversationScreenFrameSet> = {},
): ConversationScreenFrameSet {
  return { revision: 1, banner: null, strip: [frame('a'), frame('b')], ...overrides };
}

async function renderLoaded(conversationId = 'conv-1', initial = frameSet()) {
  vi.mocked(api.getConversationScreenFrames).mockResolvedValue(initial);
  const view = renderHook(() => useScreenFrames(conversationId));
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useScreenFrames', () => {
  it('loads the frame set on mount', async () => {
    const { result } = await renderLoaded();

    expect(result.current.frameSet?.strip).toHaveLength(2);
    expect(result.current.error).toBeNull();
    expect(api.getConversationScreenFrames).toHaveBeenCalledWith('conv-1');
  });

  it('does not fetch when disabled or conversationId is null', async () => {
    const { result } = renderHook(() => useScreenFrames(null));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.frameSet).toBeNull();
    expect(api.getConversationScreenFrames).not.toHaveBeenCalled();
  });

  it('surfaces a load failure instead of hanging in a loading state', async () => {
    vi.mocked(api.getConversationScreenFrames).mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useScreenFrames('conv-1'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('offline');
    expect(result.current.frameSet).toBeNull();
  });

  it('replaces local state with the server response after deleting a frame', async () => {
    const { result } = await renderLoaded();
    const updated = frameSet({ revision: 2, strip: [frame('b')] });
    vi.mocked(api.deleteScreenFrame).mockResolvedValue(updated);

    let success = false;
    await act(async () => {
      success = await result.current.deleteFrame('a');
    });

    expect(success).toBe(true);
    expect(api.deleteScreenFrame).toHaveBeenCalledWith('conv-1', 'a');
    expect(result.current.frameSet).toEqual(updated);
  });

  it('surfaces (and does not clear existing state on) a failed frame delete', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.deleteScreenFrame).mockRejectedValue(new Error('conflict'));

    let success = true;
    await act(async () => {
      success = await result.current.deleteFrame('a');
    });

    expect(success).toBe(false);
    expect(result.current.error).toBe('conflict');
    expect(result.current.frameSet?.strip).toHaveLength(2);
  });

  it('replaces local state after deleting every frame', async () => {
    const { result } = await renderLoaded();
    const emptied = frameSet({ revision: 3, banner: null, strip: [] });
    vi.mocked(api.deleteAllScreenFrames).mockResolvedValue(emptied);

    await act(async () => {
      await result.current.deleteAll();
    });

    expect(api.deleteAllScreenFrames).toHaveBeenCalledWith('conv-1');
    expect(result.current.frameSet?.strip).toHaveLength(0);
  });

  it('patches sharing and replaces local state with the response', async () => {
    const { result } = await renderLoaded();
    const updated = frameSet({ revision: 4 });
    vi.mocked(api.patchScreenFrameSharing).mockResolvedValue(updated);

    await act(async () => {
      await result.current.setSharingEnabled(false);
    });

    expect(api.patchScreenFrameSharing).toHaveBeenCalledWith('conv-1', false);
    expect(result.current.frameSet).toEqual(updated);
  });

  it('ignores a stale response for a conversation the caller has moved away from', async () => {
    vi.mocked(api.getConversationScreenFrames).mockResolvedValueOnce(frameSet());
    const { result, rerender } = renderHook(({ id }) => useScreenFrames(id), {
      initialProps: { id: 'conv-1' },
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let resolveSecond: ((value: ConversationScreenFrameSet) => void) | undefined;
    vi.mocked(api.getConversationScreenFrames).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSecond = resolve;
      }),
    );

    rerender({ id: 'conv-2' });
    await waitFor(() =>
      expect(api.getConversationScreenFrames).toHaveBeenCalledWith('conv-2'),
    );

    // Navigate away again before the in-flight request for conv-2 resolves.
    rerender({ id: 'conv-3' });
    vi.mocked(api.getConversationScreenFrames).mockResolvedValueOnce(frameSet());

    await act(async () => {
      resolveSecond?.(frameSet({ revision: 99, strip: [frame('stale')] }));
      await Promise.resolve();
    });

    // The stale conv-2 response must not have landed once conv-3 is current.
    expect(result.current.frameSet?.strip?.map((f) => f.id)).not.toEqual(['stale']);
  });

  it('silently swaps in fresh signed URLs shortly before they expire', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.setSystemTime(new Date('2026-08-24T10:00:00Z'));
      const renewed = frameSet({
        strip: [
          {
            ...frame('a'),
            content_url: 'https://example.com/a-renewed.jpg',
            url_expires_at: '2026-08-24T12:00:00Z',
          },
        ],
      });
      vi.mocked(api.getConversationScreenFrames)
        .mockReset()
        .mockResolvedValueOnce(frameSet())
        .mockResolvedValueOnce(renewed);
      const { result } = renderHook(() => useScreenFrames('conv-1'));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(58 * 60 * 1000);
      });

      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(2);
      await waitFor(() =>
        expect(result.current.frameSet?.strip?.[0]?.content_url).toBe(
          'https://example.com/a-renewed.jpg',
        ),
      );
      expect(result.current.loading).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('never lets an in-flight URL refresh resurrect frames a delete removed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.setSystemTime(new Date('2026-08-24T10:00:00Z'));
      let resolveRefresh: (set: ConversationScreenFrameSet) => void = () => {};
      vi.mocked(api.getConversationScreenFrames)
        .mockReset()
        .mockResolvedValueOnce(frameSet())
        .mockImplementationOnce(
          () =>
            new Promise<ConversationScreenFrameSet>((resolve) => {
              resolveRefresh = resolve;
            }),
        );
      vi.mocked(api.deleteScreenFrame).mockResolvedValue(
        frameSet({ strip: [frame('b')] }),
      );
      const { result } = renderHook(() => useScreenFrames('conv-1'));
      await waitFor(() => expect(result.current.loading).toBe(false));

      // The expiry refresh starts and is still waiting on the network...
      await act(async () => {
        await vi.advanceTimersByTimeAsync(58 * 60 * 1000);
      });
      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(2);

      // ...when a delete lands with the server's authoritative set.
      await act(async () => {
        await result.current.deleteFrame('a');
      });
      expect(result.current.frameSet?.strip?.map((f) => f.id)).toEqual(['b']);

      // The stale refresh response (still carrying 'a') must be discarded.
      await act(async () => {
        resolveRefresh(frameSet());
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current.frameSet?.strip?.map((f) => f.id)).toEqual(['b']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('discards a refresh that started after a delete started but resolved after it committed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.setSystemTime(new Date('2026-08-24T10:00:00Z'));
      let resolveRefresh: (set: ConversationScreenFrameSet) => void = () => {};
      let resolveDelete: (set: ConversationScreenFrameSet) => void = () => {};
      vi.mocked(api.getConversationScreenFrames)
        .mockReset()
        .mockResolvedValueOnce(frameSet())
        .mockImplementationOnce(
          () =>
            new Promise<ConversationScreenFrameSet>((resolve) => {
              resolveRefresh = resolve;
            }),
        );
      vi.mocked(api.deleteScreenFrame)
        .mockReset()
        .mockImplementationOnce(
          () =>
            new Promise<ConversationScreenFrameSet>((resolve) => {
              resolveDelete = resolve;
            }),
        );
      const { result } = renderHook(() => useScreenFrames('conv-1'));
      await waitFor(() => expect(result.current.loading).toBe(false));

      // 1. The delete starts and waits on the network.
      let deletion: Promise<boolean> = Promise.resolve(false);
      act(() => {
        deletion = result.current.deleteFrame('a');
      });
      // 2. The expiry refresh starts after it (sees the already-bumped state).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(58 * 60 * 1000);
      });
      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(2);
      // 3. The delete commits first...
      await act(async () => {
        resolveDelete(frameSet({ strip: [frame('b')] }));
        await deletion;
      });
      expect(result.current.frameSet?.strip?.map((f) => f.id)).toEqual(['b']);
      // 4. ...then the older GET lands. It must not bring 'a' back.
      await act(async () => {
        resolveRefresh(frameSet());
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current.frameSet?.strip?.map((f) => f.id)).toEqual(['b']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('rearms renewal when a failed delete discards an in-flight renewal', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.setSystemTime(new Date('2026-08-24T10:00:00Z'));
      let resolveRefresh: (set: ConversationScreenFrameSet) => void = () => {};
      const renewed = frameSet({
        strip: [
          {
            ...frame('a'),
            content_url: 'https://example.com/a-renewed.jpg',
            url_expires_at: '2026-08-24T12:00:00Z',
          },
        ],
      });
      vi.mocked(api.getConversationScreenFrames)
        .mockReset()
        .mockResolvedValueOnce(frameSet())
        .mockImplementationOnce(
          () =>
            new Promise<ConversationScreenFrameSet>((resolve) => {
              resolveRefresh = resolve;
            }),
        )
        .mockResolvedValue(renewed);
      vi.mocked(api.deleteScreenFrame)
        .mockReset()
        .mockRejectedValueOnce(new Error('offline'));
      const { result } = renderHook(() => useScreenFrames('conv-1'));
      await waitFor(() => expect(result.current.loading).toBe(false));

      // Renewal in flight...
      await act(async () => {
        await vi.advanceTimersByTimeAsync(58 * 60 * 1000);
      });
      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(2);
      // ...a delete starts and fails, which fences the renewal out...
      await act(async () => {
        await result.current.deleteFrame('a');
      });
      await act(async () => {
        resolveRefresh(renewed);
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current.frameSet?.strip?.[0]?.content_url).toBe(
        'https://example.com/a.jpg',
      );

      // ...so renewal must be retried rather than never rearmed.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60 * 1000);
      });
      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(3);
      await waitFor(() =>
        expect(result.current.frameSet?.strip?.[0]?.content_url).toBe(
          'https://example.com/a-renewed.jpg',
        ),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('retries a failed renewal with backoff instead of giving up', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.setSystemTime(new Date('2026-08-24T10:00:00Z'));
      vi.mocked(api.getConversationScreenFrames)
        .mockReset()
        .mockResolvedValueOnce(frameSet())
        .mockRejectedValueOnce(new Error('offline'))
        .mockResolvedValue(
          frameSet({
            strip: [{ ...frame('a'), url_expires_at: '2026-08-24T12:00:00Z' }],
          }),
        );
      const { result } = renderHook(() => useScreenFrames('conv-1'));
      await waitFor(() => expect(result.current.loading).toBe(false));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(58 * 60 * 1000);
      });
      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(2);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2 * 60 * 1000);
      });
      expect(api.getConversationScreenFrames).toHaveBeenCalledTimes(3);
      await waitFor(() =>
        expect(result.current.frameSet?.strip?.[0]?.url_expires_at).toBe(
          '2026-08-24T12:00:00Z',
        ),
      );
    } finally {
      vi.useRealTimers();
    }
  });
});
