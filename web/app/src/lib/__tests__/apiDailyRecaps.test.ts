import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHttpError, createDailySummary } from '@/lib/api';

vi.mock('@/lib/firebase', () => ({
  getIdToken: vi.fn().mockResolvedValue('test-token'),
}));
vi.mock('@/lib/clientDevice', () => ({
  getWebDeviceIdHash: vi.fn().mockResolvedValue('test-device'),
}));

describe('date-based recap creation', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('uses the creation endpoint and returns a complete recap without push plumbing', async () => {
    const recap = { id: 'recap-1', date: '2026-10-04', headline: 'Recovered day' };
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify(recap), { status: 200 }));
    expect(await createDailySummary('2026-10-04')).toEqual(recap);
    expect(fetch.mock.calls[0][0]).toBe('/api/proxy/v1/users/daily-summaries');
    const request = fetch.mock.calls[0][1]!;
    expect(request.method).toBe('POST');
    expect(JSON.parse(request.body as string)).toEqual({ date: '2026-10-04' });
  });

  it.each([400, 402, 409, 422, 429, 500])(
    'preserves status %i for the recovery UI',
    async (status) => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status }));
      await expect(createDailySummary('2026-10-04')).rejects.toMatchObject({ status });
      await expect(createDailySummary('2026-10-04')).rejects.toBeInstanceOf(ApiHttpError);
    },
  );

  it.each([
    { summary_id: 'legacy-test-response' },
    { id: 'wrong-day', date: '2026-10-05' },
  ])('rejects an unusable response', async (body) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200 }),
    );
    await expect(createDailySummary('2026-10-04')).rejects.toThrow(
      'Invalid recap response',
    );
  });
});
