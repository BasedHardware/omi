import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MessageFile } from '@/types/conversation';

vi.mock('@/lib/api', () => ({
  getMessages: vi.fn(),
  sendMessageStream: vi.fn(),
  clearMessages: vi.fn(),
  saveRealtimeMessage: vi.fn(),
}));

const { getMessages, sendMessageStream, saveRealtimeMessage } = await import('@/lib/api');
const { useChat } = await import('@/hooks/useChat');

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function aiMessage(id: string, text: string) {
  return {
    id,
    created_at: new Date().toISOString(),
    text,
    sender: 'ai' as const,
    type: 'text' as const,
    from_external_integration: false,
    files: [],
    memories: [],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useChat session ownership', () => {
  it('drops a history response that belongs to the previously selected session', async () => {
    const first = deferred<ReturnType<typeof aiMessage>[]>();
    const second = deferred<ReturnType<typeof aiMessage>[]>();
    vi.mocked(getMessages)
      .mockReturnValueOnce(first.promise as never)
      .mockReturnValueOnce(second.promise as never);

    const { result, rerender } = renderHook(
      ({ sessionId }: { sessionId: string }) => useChat({ chatSessionId: sessionId }),
      { initialProps: { sessionId: 'sess-a' } },
    );

    await act(async () => {
      void result.current.loadHistory();
    });

    rerender({ sessionId: 'sess-b' });

    await act(async () => {
      void result.current.loadHistory();
      // The abandoned session answers last — the case where an unguarded
      // response overwrites the transcript of the session now on screen.
      second.resolve([aiMessage('b1', 'from session B')]);
      await Promise.resolve();
      first.resolve([aiMessage('a1', 'from session A')]);
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.messages).toHaveLength(1));
    expect(result.current.messages[0]?.text).toBe('from session B');
  });

  it('drops stream chunks that arrive after the reader switched sessions', async () => {
    vi.mocked(getMessages).mockResolvedValue([] as never);

    let emit: (chunk: {
      type: string;
      text: string;
      message?: unknown;
    }) => void = () => {};
    const streamDone = deferred<void>();
    vi.mocked(sendMessageStream).mockImplementation((async (
      _text: string,
      onChunk: (chunk: { type: string; text: string; message?: unknown }) => void,
    ) => {
      emit = onChunk;
      await streamDone.promise;
    }) as never);

    const { result, rerender } = renderHook(
      ({ sessionId }: { sessionId: string }) => useChat({ chatSessionId: sessionId }),
      { initialProps: { sessionId: 'sess-a' } },
    );

    await act(async () => {
      void result.current.sendMessage('hello');
    });

    rerender({ sessionId: 'sess-b' });

    await act(async () => {
      emit({ type: 'data', text: 'late answer for A' });
      emit({ type: 'done', text: '', message: aiMessage('a-final', 'A final') });
      streamDone.resolve();
      await Promise.resolve();
    });

    expect(result.current.streamingText).toBe('');
    expect(result.current.messages).toHaveLength(0);
  });

  it('adds and persists Gemini Live turns in the selected chat session', async () => {
    vi.mocked(saveRealtimeMessage).mockImplementation(async (params) => ({
      id: params.clientMessageId,
      created_at: '2026-08-11T00:00:00Z',
      session_id: 'sess-live',
    }));
    const { result } = renderHook(() =>
      useChat({ appId: 'app-1', chatSessionId: 'sess-live' }),
    );

    await act(async () => {
      await result.current.appendRealtimeExchange('Hello Omi', 'Hello there');
    });

    expect(result.current.messages.map((message) => message.text)).toEqual([
      'Hello Omi',
      'Hello there',
    ]);
    expect(saveRealtimeMessage).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        text: 'Hello Omi',
        sender: 'human',
        appId: 'app-1',
        sessionId: 'sess-live',
      }),
    );
    expect(saveRealtimeMessage).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        text: 'Hello there',
        sender: 'ai',
        appId: 'app-1',
        sessionId: 'sess-live',
      }),
    );
  });

  it('renders uploaded files in an optimistic attachment-only message', async () => {
    vi.mocked(sendMessageStream).mockResolvedValue(undefined as never);
    const attachment: MessageFile = {
      id: 'file-1',
      name: 'notes.txt',
      created_at: '2026-08-11T00:00:00Z',
      mime_type: 'text/plain',
      openai_file_id: 'openai-file-1',
    };
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('', [attachment.id], undefined, [attachment]);
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({
      text: '',
      sender: 'human',
      files: [attachment],
    });
  });

  it('keeps ID-only attachment sends visible in the optimistic message', async () => {
    vi.mocked(sendMessageStream).mockResolvedValue(undefined as never);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('', ['file-2']);
    });

    expect(result.current.messages[0]?.files).toEqual([
      expect.objectContaining({ id: 'file-2', name: 'Attached file' }),
    ]);
  });
});
