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
});
