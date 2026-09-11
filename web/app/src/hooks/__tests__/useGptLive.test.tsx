import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const doubles = vi.hoisted(() => ({
  clients: [] as Array<{
    options: {
      onReady: () => void;
      onClose: () => void;
    };
    connect: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
    pause: ReturnType<typeof vi.fn>;
    resume: ReturnType<typeof vi.fn>;
  }>,
}));

vi.mock('@/lib/api', () => ({
  createGptLiveSession: vi.fn(async () => ({ token: 'session-token' })),
  reportGptLiveUsage: vi.fn(async () => undefined),
}));

vi.mock('@/lib/gptLive', () => ({
  DEFAULT_GPT_LIVE_INSTRUCTIONS: 'You are Omi.',
  createGptLiveClient: (options: (typeof doubles.clients)[number]['options']) => {
    const client = {
      options,
      connect: vi.fn(),
      stop: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
    };
    doubles.clients.push(client);
    return client;
  },
}));

const { useGptLive } = await import('@/hooks/useGptLive');

beforeEach(() => {
  vi.clearAllMocks();
  doubles.clients = [];
});

describe('useGptLive session ownership', () => {
  it('ignores a retired client closing after its replacement becomes live', async () => {
    const { result } = renderHook(() =>
      useGptLive({ messages: [], onExchange: vi.fn(async () => undefined) }),
    );

    await act(async () => {
      await result.current.start();
    });
    const retired = doubles.clients[0]!;

    act(() => result.current.stop());
    await act(async () => {
      await result.current.start();
    });
    const replacement = doubles.clients[1]!;
    act(() => replacement.options.onReady());
    await waitFor(() => expect(result.current.state).toBe('listening'));

    act(() => retired.options.onClose());

    expect(result.current.state).toBe('listening');
    expect(replacement.connect).toHaveBeenCalledWith('session-token');
  });
});
