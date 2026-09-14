import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));

import {
  STATIC_MAP_MAX_PINS,
  fetchStaticMap,
  normalizeStaticMapPins,
  staticMapAxisPx,
  staticMapPath,
  staticMapPinsParam,
  type MapPin,
} from '@/lib/staticMap';

describe('static map request shape', () => {
  it('quantizes pins to four decimals and drops pins that collapse onto an earlier one', () => {
    expect(
      staticMapPinsParam([
        { latitude: 37.77493, longitude: -122.41942 },
        { latitude: 37.77491, longitude: -122.41939 },
        { latitude: 40.7128, longitude: -74.006 },
      ]),
    ).toBe('37.7749,-122.4194|40.7128,-74.0060');
  });

  it('skips pins without real coordinates instead of throwing', () => {
    // Recap pins are Optional[float] on the wire, so null reaches the client.
    const pins = [
      { latitude: null, longitude: -122.4 },
      { latitude: 37.7749, longitude: undefined },
      { latitude: Number.NaN, longitude: 1 },
      { latitude: 91, longitude: 0 },
      { latitude: 40.7128, longitude: -74.006 },
    ] as unknown as MapPin[];

    expect(() => staticMapPinsParam(pins)).not.toThrow();
    expect(staticMapPinsParam(pins)).toBe('40.7128,-74.0060');
  });

  it('caps the request at the backend pin limit', () => {
    const pins = Array.from({ length: 60 }, (_, index) => ({
      latitude: index,
      longitude: index,
    }));
    expect(staticMapPinsParam(pins).split('|')).toHaveLength(STATIC_MAP_MAX_PINS);
  });

  it('keeps the first original pin of each quantized cell for the fallback render', () => {
    const first = { latitude: 37.77493, longitude: -122.41942 };
    expect(
      normalizeStaticMapPins([first, { latitude: 37.77491, longitude: -122.41939 }]),
    ).toEqual([first]);
  });

  it('steps sizes up to shared buckets inside the backend bounds', () => {
    expect(staticMapAxisPx(180)).toBe(200);
    expect(staticMapAxisPx(200)).toBe(200);
    expect(staticMapAxisPx(10)).toBe(64);
    expect(staticMapAxisPx(5000)).toBe(1280);
  });

  it('encodes the pin list into the backend path', () => {
    expect(staticMapPath('37.7749,-122.4194|40.7128,-74.0060', 320, 200)).toBe(
      '/v1/static-map?pins=37.7749%2C-122.4194%7C40.7128%2C-74.0060&width=320&height=200',
    );
  });
});

describe('fetchStaticMap', () => {
  beforeEach(() => {
    getIdToken.mockReset();
    vi.unstubAllGlobals();
  });

  it('requests the image through the same-origin proxy with the session token', async () => {
    getIdToken.mockResolvedValue('test-token');
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(new Uint8Array([0x89, 0x50, 0x4e, 0x47]), {
          headers: { 'content-type': 'image/png' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const blob = await fetchStaticMap(
      '/v1/static-map?pins=1.0000%2C2.0000&width=64&height=64',
    );

    expect(blob?.size).toBe(4);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/proxy/v1/static-map?pins=1.0000%2C2.0000&width=64&height=64',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    );
  });

  it('resolves null without calling the proxy when signed out', async () => {
    getIdToken.mockResolvedValue(null);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      fetchStaticMap('/v1/static-map?pins=1%2C1&width=64&height=64'),
    ).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('resolves null when the backend cannot render the map', async () => {
    getIdToken.mockResolvedValue('test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ detail: 'Static map is temporarily unavailable' }),
            {
              status: 502,
              headers: { 'content-type': 'application/json' },
            },
          ),
      ),
    );

    await expect(
      fetchStaticMap('/v1/static-map?pins=1%2C1&width=64&height=64'),
    ).resolves.toBeNull();
  });
});
