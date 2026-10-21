import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));

import { StaticMapPreview } from '@/components/ui/StaticMapPreview';
import type { MapPin } from '@/lib/staticMap';

class ImmediateResizeObserver {
  callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element) {
    this.callback(
      [
        {
          target,
          contentRect: { width: 320, height: 180 },
        } as unknown as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }

  unobserve() {}

  disconnect() {}
}

const pins = [{ latitude: 37.77493, longitude: -122.41942 }];
const createObjectURL = vi.fn(() => 'blob:static-map');
const revokeObjectURL = vi.fn();
// jsdom may not define these; restore whatever was there so the patch never
// leaks into other suites.
const originalCreateObjectURL = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
const originalRevokeObjectURL = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');

function restoreUrlStatic(
  name: 'createObjectURL' | 'revokeObjectURL',
  descriptor?: PropertyDescriptor,
) {
  if (descriptor) {
    Object.defineProperty(URL, name, descriptor);
  } else {
    delete (URL as unknown as Record<string, unknown>)[name];
  }
}

function flushPending() {
  return act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
}

function pngResponse() {
  return new Response(new Uint8Array([0x89, 0x50, 0x4e, 0x47]), {
    headers: { 'content-type': 'image/png' },
  });
}

beforeEach(() => {
  getIdToken.mockReset();
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  vi.stubGlobal('ResizeObserver', ImmediateResizeObserver);
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: revokeObjectURL,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  restoreUrlStatic('createObjectURL', originalCreateObjectURL);
  restoreUrlStatic('revokeObjectURL', originalRevokeObjectURL);
});

describe('StaticMapPreview', () => {
  it('shows the backend-rendered map once the authenticated fetch resolves', async () => {
    getIdToken.mockResolvedValue('test-token');
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      pngResponse(),
    );
    vi.stubGlobal('fetch', fetchMock);

    render(<StaticMapPreview pins={pins} alt="Conversation location" />);

    expect(await screen.findByTestId('static-map-fallback')).toBeInTheDocument();
    expect(await screen.findByTestId('static-map-image')).toHaveAttribute(
      'src',
      'blob:static-map',
    );
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      '/api/proxy/v1/static-map?pins=37.7749%2C-122.4194&width=320&height=200',
    );
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      headers: { Authorization: 'Bearer test-token' },
    });
  });

  it('names the map for screen readers while only the fallback is showing', async () => {
    getIdToken.mockResolvedValue(null);
    vi.stubGlobal('fetch', vi.fn());

    render(<StaticMapPreview pins={pins} alt="Conversation location" />);
    await flushPending();

    expect(
      screen.getByRole('img', { name: 'Conversation location' }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('static-map-image')).toBeNull();
  });

  it('is decorative when a wrapping control already names it', async () => {
    getIdToken.mockResolvedValue('test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => pngResponse()),
    );

    render(<StaticMapPreview pins={pins} alt="" />);
    await screen.findByTestId('static-map-image');

    expect(screen.queryByRole('img')).toBeNull();
  });

  it('draws the fallback from the same normalized pins the request uses', async () => {
    getIdToken.mockResolvedValue(null);
    vi.stubGlobal('fetch', vi.fn());
    const noisyPins = [
      { latitude: 37.77493, longitude: -122.41942 },
      { latitude: 37.77491, longitude: -122.41939 },
      { latitude: null, longitude: 0 },
      ...Array.from({ length: 60 }, (_, index) => ({
        latitude: index,
        longitude: index,
      })),
    ] as unknown as MapPin[];

    render(<StaticMapPreview pins={noisyPins} alt="Recap locations" />);

    const fallback = await screen.findByTestId('static-map-fallback');
    expect(fallback.querySelectorAll('circle')).toHaveLength(50);
  });

  it('keeps the pin-dot canvas when the backend cannot render the map', async () => {
    getIdToken.mockResolvedValue('test-token');
    const fetchMock = vi.fn(async () => new Response('{}', { status: 502 }));
    vi.stubGlobal('fetch', fetchMock);

    render(<StaticMapPreview pins={pins} alt="Conversation location" />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await flushPending();
    expect(screen.getByTestId('static-map-fallback')).toBeInTheDocument();
    expect(screen.queryByTestId('static-map-image')).toBeNull();
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it('does not call the proxy while signed out', async () => {
    getIdToken.mockResolvedValue(null);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(<StaticMapPreview pins={pins} alt="Conversation location" />);

    await waitFor(() => expect(getIdToken).toHaveBeenCalled());
    await flushPending();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByTestId('static-map-fallback')).toBeInTheDocument();
  });

  it('releases the object URL on unmount', async () => {
    getIdToken.mockResolvedValue('test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => pngResponse()),
    );

    const { unmount } = render(
      <StaticMapPreview pins={pins} alt="Conversation location" />,
    );
    await screen.findByTestId('static-map-image');

    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:static-map');
  });
});
