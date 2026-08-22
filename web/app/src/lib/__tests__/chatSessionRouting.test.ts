import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/firebase', () => ({ getIdToken: vi.fn().mockResolvedValue('t') }));
vi.mock('@/lib/clientDevice', () => ({
  getWebDeviceIdHash: vi.fn().mockResolvedValue('device'),
}));

const {
  clearMessages,
  getMessages,
  sendMessageStream,
  createGeminiLiveSession,
  saveRealtimeMessage,
  reportGeminiLiveUsage,
} = await import('@/lib/api');

/**
 * Every `/v2/messages` call must carry the session the reader has selected.
 *
 * Reads were wired up first and sends were not, so choosing an older chat
 * displayed that thread while the message and its reply persisted to the
 * default shared session — the client-side version of the mis-routing the
 * backend's explicit-id contract exists to prevent.
 */

function requestedUrls(): string[] {
  return vi.mocked(fetch).mock.calls.map(([input]) => String(input));
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      text: async () => '',
      // sendMessageStream reads the body as a stream; an empty one ends the
      // read immediately without exercising chunk parsing.
      body: {
        getReader: () => ({
          read: async () => ({ done: true, value: undefined }),
          releaseLock: () => {},
        }),
      },
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('chat session routing', () => {
  it('reads the selected session', async () => {
    await getMessages(undefined, 'sess-9');

    expect(requestedUrls()[0]).toContain('chat_session_id=sess-9');
  });

  it('sends into the selected session', async () => {
    await sendMessageStream('hello', () => {}, { chatSessionId: 'sess-9' });

    expect(requestedUrls()[0]).toContain('chat_session_id=sess-9');
  });

  it('clears the selected session', async () => {
    await clearMessages(undefined, 'sess-9');

    expect(requestedUrls()[0]).toContain('chat_session_id=sess-9');
  });

  it('omits the parameter for the default shared thread on every verb', async () => {
    await getMessages();
    await sendMessageStream('hello', () => {});
    await clearMessages();

    for (const url of requestedUrls()) {
      expect(url).not.toContain('chat_session_id');
    }
  });

  it('omits the parameter when the session is explicitly null', async () => {
    await getMessages(undefined, null);
    await clearMessages(undefined, null);
    await sendMessageStream('hello', () => {}, { chatSessionId: null });

    for (const url of requestedUrls()) {
      expect(url).not.toContain('chat_session_id');
    }
  });

  it('keeps app_id alongside the session id', async () => {
    await getMessages('app-1', 'sess-9');

    const url = requestedUrls()[0];
    expect(url).toContain('app_id=app-1');
    expect(url).toContain('chat_session_id=sess-9');
  });

  it('mints managed Gemini Live sessions through the authenticated proxy', async () => {
    await createGeminiLiveSession();

    const [url, request] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toBe('/api/proxy/v2/realtime/session');
    expect(request?.method).toBe('POST');
    expect(JSON.parse(String(request?.body))).toEqual({ provider: 'gemini' });
  });

  it('persists live turns into the selected chat history', async () => {
    await saveRealtimeMessage({
      text: 'Hello Omi',
      sender: 'human',
      clientMessageId: 'live-1',
      appId: 'app-1',
      sessionId: 'sess-9',
    });

    const [url, request] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toBe('/api/proxy/v2/desktop/messages');
    expect(JSON.parse(String(request?.body))).toEqual({
      text: 'Hello Omi',
      sender: 'human',
      app_id: 'app-1',
      session_id: 'sess-9',
      client_message_id: 'live-1',
      message_source: 'realtime_voice',
    });
  });

  it('reports managed Gemini Live usage', async () => {
    await reportGeminiLiveUsage({
      input_text_tokens: 1,
      input_audio_tokens: 2,
      input_cached_tokens: 3,
      output_text_tokens: 4,
      output_audio_tokens: 5,
    });

    const [url, request] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toBe('/api/proxy/v2/realtime/usage');
    expect(JSON.parse(String(request?.body))).toEqual({
      provider: 'gemini',
      model: 'gemini-3.1-flash-live-preview',
      input_text_tokens: 1,
      input_audio_tokens: 2,
      input_cached_tokens: 3,
      output_text_tokens: 4,
      output_audio_tokens: 5,
    });
  });
});
