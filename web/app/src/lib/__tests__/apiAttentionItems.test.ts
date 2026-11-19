import { afterEach, beforeEach, expect, it, vi } from 'vitest';
vi.mock('@/lib/firebase', () => ({ getIdToken: vi.fn(async () => 'fixture-token') }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash: vi.fn(async () => null) }));
import { ApiHttpError, getAttentionItems, retryAttentionItem } from '@/lib/api';
const fetchMock = vi.fn();
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());
it('uses the ledger contract and sends encoded item id and idempotency key, never general reprocess', async () => {
  fetchMock.mockResolvedValueOnce(new Response('{"items":[]}'));
  expect(await getAttentionItems()).toEqual({ items: [] });
  fetchMock.mockResolvedValueOnce(
    new Response('{"operation_id":"op","state":"succeeded"}'),
  );
  expect(await retryAttentionItem('notes:/x', 'same-key')).toEqual({
    operation_id: 'op',
    state: 'succeeded',
  });
  expect(fetchMock.mock.calls[0][0]).toBe('/api/proxy/v1/attention-items');
  expect(fetchMock.mock.calls[1][0]).toBe(
    '/api/proxy/v1/attention-items/notes%3A%2Fx/retry',
  );
  expect(fetchMock.mock.calls[1][1].method).toBe('POST');
  expect(new Headers(fetchMock.mock.calls[1][1].headers).get('Idempotency-Key')).toBe(
    'same-key',
  );
});
it('409 not_retryable rejects with its HTTP status', async () => {
  fetchMock.mockResolvedValueOnce(
    new Response('{"state":"not_retryable"}', { status: 409 }),
  );
  await expect(retryAttentionItem('notes', 'key')).rejects.toMatchObject({
    status: 409,
    state: 'not_retryable',
  });
});

it.each(['{"detail":{"state":"not_retryable"}}', 'proxy unavailable'])(
  'retains terminal state only when the error body provides it: %s',
  async (body) => {
    fetchMock.mockResolvedValueOnce(new Response(body, { status: 409 }));
    await expect(retryAttentionItem('notes', 'key')).rejects.toMatchObject({
      status: 409,
      state: body.startsWith('{') ? 'not_retryable' : undefined,
    });
  },
);
