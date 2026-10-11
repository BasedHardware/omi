import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));
const { getWebDeviceIdHash } = vi.hoisted(() => ({ getWebDeviceIdHash: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash }));

import { deleteScreenFrame, getConversationScreenFrames } from '@/lib/api';

function frameSet(ids: string[]) {
  return {
    revision: 1,
    banner: null,
    strip: ids.map((id) => ({
      id,
      captured_at: '2026-08-24T10:00:00Z',
      role: 'strip',
      rank: 0,
      caption: id,
      labels: [],
      width: 1600,
      height: 900,
      content_url: `https://example.com/${id}.jpg`,
      thumbnail_url: `https://example.com/${id}_t.jpg`,
      url_expires_at: '2026-08-24T11:00:00Z',
      ground: { stops: ['#101010', '#202020'], is_neutral: false },
    })),
  };
}

describe('screen-frame set fetches are never cached', () => {
  beforeEach(() => {
    getIdToken.mockResolvedValue('test-token');
    getWebDeviceIdHash.mockResolvedValue(null);
    vi.unstubAllGlobals();
  });

  it('a GET that resolves after a DELETE cannot seed a cached set that a reopen serves', async () => {
    let releaseStaleGet: () => void = () => {};
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'DELETE') {
        return new Response(JSON.stringify(frameSet(['b'])), { status: 200 });
      }
      if (fetchMock.mock.calls.length === 1) {
        // The in-flight renewal GET, answered with the pre-delete set.
        await new Promise<void>((resolve) => {
          releaseStaleGet = resolve;
        });
        return new Response(JSON.stringify(frameSet(['a', 'b'])), { status: 200 });
      }
      return new Response(JSON.stringify(frameSet(['b'])), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const staleGet = getConversationScreenFrames('conv-cache');
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await deleteScreenFrame('conv-cache', 'a');
    releaseStaleGet();
    await staleGet;

    // Reopening the conversation must hit the server, not the stale response.
    const reopened = await getConversationScreenFrames('conv-cache');
    expect(reopened.strip?.map((f) => f.id)).toEqual(['b']);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
