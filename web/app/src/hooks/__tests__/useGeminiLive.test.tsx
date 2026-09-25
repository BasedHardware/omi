import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const doubles = vi.hoisted(() => ({
  clients: [] as Array<{
    callbacks: {
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
  createGeminiLiveSession: vi.fn(async () => ({ token: 'session-token' })),
  reportGeminiLiveUsage: vi.fn(async () => undefined),
}));

vi.mock('@/lib/geminiLive', () => ({
  GeminiLiveClient: class {
    connect = vi.fn();
    stop = vi.fn();
    pause = vi.fn();
    resume = vi.fn();

    constructor(
      readonly callbacks: {
        onReady: () => void;
        onClose: () => void;
      },
    ) {
      doubles.clients.push(this);
    }
  },
}));

const { useGeminiLive } = await import('@/hooks/useGeminiLive');

beforeEach(() => {
  vi.clearAllMocks();
  doubles.clients = [];
});

describe('useGeminiLive session ownership', () => {
  it('ignores a retired client closing after its replacement becomes live', async () => {
    const { result } = renderHook(() =>
      useGeminiLive({ messages: [], onExchange: vi.fn(async () => undefined) }),
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
    act(() => replacement.callbacks.onReady());
    await waitFor(() => expect(result.current.state).toBe('listening'));

    act(() => retired.callbacks.onClose());

    expect(result.current.state).toBe('listening');
    expect(replacement.connect).toHaveBeenCalledWith('session-token');
  });
});
