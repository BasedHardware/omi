import {
  ChatBackendError,
  cancelChatGeneration,
  chatErrorCopy,
  loadChatHistory,
  loadNewestChatHistory,
  loadOlderChatHistory,
  mergeOlderChatHistory,
  parseTerminal,
  reconcileCanonicalChatHistory,
  sendChatMessage,
} from '../src/chatClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNative';
import type {ChatMessage} from '../src/chatClient';

test('loads main Chat history through the native boundary', async () => {
  const requests: NativeHttpRequest[] = [];
  const backend = {
    request: async (request: NativeHttpRequest) => {
      requests.push(request);
      return {
        id: request.id,
        status: 200,
        body: '{"messages":[],"page":{"olderCursor":null,"hasOlder":false}}',
      };
    },
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  } satisfies OmiBackend;

  await expect(loadChatHistory(backend)).resolves.toEqual([]);
  expect(requests[0].path).toBe('/v1/chat-messages?limit=50');
});

test('admits one main-scope human message and accepts only a terminal SSE message', async () => {
  const requests: NativeHttpRequest[] = [];
  const human = {
    id: 'desktop-100-1',
    text: 'Hello',
    sender: 'human',
    createdAt: 100,
    generationOutcome: null,
  };
  const assistant = {
    id: 'assistant-1',
    text: 'Hi.',
    sender: 'ai',
    createdAt: 101,
    generationOutcome: 'completed',
  };
  const backend = {
    request: async (request: NativeHttpRequest) => {
      requests.push(request);
      return {
        id: request.id,
        status: 201,
        body: JSON.stringify({
          message: human,
          generation: {id: 'generation-1'},
        }),
      };
    },
    generationEvents: async (generationId, lastEventId) => {
      expect(generationId).toBe('generation-1');
      expect(lastEventId).toBeNull();
      return {
        id: generationId,
        status: 200,
        body: `event: snapshot\nid: e1\ndata: {"kind":"snapshot","text":"H"}\n\nevent: done\nid: e2\ndata: ${JSON.stringify(
          {kind: 'done', message: assistant},
        )}\n\n`,
      };
    },
    cancelGenerationEvents: async () => {},
  } satisfies OmiBackend;

  const onGenerationStarted = jest.fn();
  await expect(
    sendChatMessage(backend, 'Hello', 100, onGenerationStarted),
  ).resolves.toEqual({
    human,
    assistant,
  });
  expect(onGenerationStarted).toHaveBeenCalledWith('generation-1');
  expect(JSON.parse(requests[0].body!)).toEqual(
    expect.objectContaining({
      appId: null,
      chatSessionId: null,
      sender: 'human',
    }),
  );
});

test('fails closed when SSE ends without a terminal frame', () => {
  expect(() =>
    parseTerminal(
      'event: delta\nid: e1\ndata: {"kind":"delta","text":"partial"}\n\n',
    ),
  ).toThrow('without a terminal');
});

test('represents a failed generation as a stable assistant delivery', async () => {
  const human = {
    id: 'desktop-failed',
    text: 'Keep this',
    sender: 'human' as const,
    createdAt: 400,
    generationOutcome: null,
  };
  const backend = {
    request: async (request: NativeHttpRequest) => ({
      id: request.id,
      status: 201,
      body: JSON.stringify({
        message: human,
        generation: {id: 'generation-failed'},
      }),
    }),
    generationEvents: async () => ({
      id: 'generation-failed',
      status: 200,
      body: 'event: failed\nid: terminal\ndata: {"kind":"failed","error":{"code":"provider_failed","retryable":true}}\n\n',
    }),
    cancelGenerationEvents: async () => {},
  } satisfies OmiBackend;

  await expect(sendChatMessage(backend, 'Keep this', 400)).resolves.toEqual({
    human,
    assistant: {
      id: 'generation:generation-failed',
      text: '',
      sender: 'ai',
      createdAt: 400,
      generationOutcome: 'failed',
      generationId: 'generation-failed',
      generationRetryable: true,
    },
  });
});

test('reconciles canonical history when native reconnect reports replay expiry', async () => {
  const human = {
    id: 'desktop-200-2',
    text: 'Recover',
    sender: 'human' as const,
    createdAt: 200,
    generationOutcome: null,
  };
  const assistant = {
    id: 'assistant-recovered',
    text: 'Recovered.',
    sender: 'ai' as const,
    createdAt: 201,
    generationOutcome: 'completed' as const,
  };
  let requests = 0;
  const backend = {
    request: async (request: NativeHttpRequest) => {
      requests += 1;
      return requests === 1
        ? {
            id: request.id,
            status: 201,
            body: JSON.stringify({
              message: human,
              generation: {id: 'generation-expired'},
            }),
          }
        : {
            id: request.id,
            status: 200,
            body: JSON.stringify({
              messages: [human, assistant],
              page: {olderCursor: null, hasOlder: false},
            }),
          };
    },
    generationEvents: async () => ({
      id: 'expired',
      status: 410,
      body: '{"error":{"code":"generation_replay_expired","retryable":false,"action":"refresh_history"}}',
    }),
    cancelGenerationEvents: async () => {},
  } satisfies OmiBackend;

  await expect(sendChatMessage(backend, 'Recover', 200)).resolves.toEqual({
    human,
    assistant,
  });
});

test('durable cancellation leaves terminal reconciliation to the active stream', async () => {
  const order: string[] = [];
  const backend = {
    request: async (request: NativeHttpRequest) => ({
      id: request.id,
      status: 200,
      body: JSON.stringify({
        messages: [],
        page: {olderCursor: null, hasOlder: false},
      }),
    }),
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async generationId => {
      expect(generationId).toBe('generation-cancel');
      order.push('delete');
    },
  } satisfies OmiBackend;

  await expect(
    cancelChatGeneration(backend, 'generation-cancel'),
  ).resolves.toBeUndefined();
  expect(order).toEqual(['delete']);
});

test('native observer cancellation reconnects for the canonical terminal frame', async () => {
  const human = {
    id: 'desktop-300-3',
    text: 'Stop',
    sender: 'human' as const,
    createdAt: 300,
    generationOutcome: null,
  };
  const assistant = {
    id: 'assistant-cancelled',
    text: 'Partial',
    sender: 'ai' as const,
    createdAt: 301,
    generationOutcome: 'cancelled' as const,
  };
  let streams = 0;
  const backend = {
    request: async (request: NativeHttpRequest) => ({
      id: request.id,
      status: 201,
      body: JSON.stringify({message: human, generation: {id: 'generation-3'}}),
    }),
    generationEvents: async () => {
      streams += 1;
      if (streams === 1) {
        throw Object.assign(new Error('closed after durable delete'), {
          code: 'OMI_HTTP_CANCELLED',
        });
      }
      return {
        id: 'generation-3',
        status: 200,
        body: `event: cancelled\nid: e3\ndata: ${JSON.stringify({
          kind: 'cancelled',
          message: assistant,
        })}\n\n`,
      };
    },
    cancelGenerationEvents: async () => {},
  } satisfies OmiBackend;

  await expect(sendChatMessage(backend, 'Stop', 300)).resolves.toEqual({
    human,
    assistant,
  });
  expect(streams).toBe(2);
});

test('maps ratified public recovery without automatically retrying', () => {
  expect(
    chatErrorCopy(
      new ChatBackendError(401, 'unauthorized', false, 'reauthenticate', null),
    ),
  ).toBe('Sign in again to continue.');
  expect(
    chatErrorCopy(new ChatBackendError(429, 'rate_limited', true, 'retry', 12)),
  ).toBe('Too many requests. Try again in 12 seconds.');
  expect(
    chatErrorCopy(
      new ChatBackendError(503, 'service_unavailable', true, 'retry', 2),
    ),
  ).toBe('Omi is temporarily unavailable. Try again.');
  expect(
    chatErrorCopy(new ChatBackendError(404, 'not_found', false, 'none', null)),
  ).toBe('This request cannot be completed.');
});

test('loads opaque older cursors and preserves exact page metadata', async () => {
  const paths: string[] = [];
  const olderCursor = 'opaque/+ cursor=';
  const backend = {
    request: async (request: NativeHttpRequest) => {
      paths.push(request.path);
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          messages: [],
          page: {olderCursor, hasOlder: true},
        }),
      };
    },
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  } satisfies OmiBackend;

  await expect(loadNewestChatHistory(backend)).resolves.toEqual({
    messages: [],
    olderCursor,
    hasOlder: true,
  });
  await loadOlderChatHistory(backend, olderCursor);
  expect(paths[1]).toBe(
    `/v1/chat-messages?limit=50&olderCursor=${encodeURIComponent(olderCursor)}`,
  );
});

test('merges older pages idempotently without sorting server order', () => {
  const message = (id: string, createdAt: number): ChatMessage => ({
    id,
    text: id,
    sender: 'human',
    createdAt,
    generationOutcome: null,
  });
  const current = [message('c', 1), message('d', 2)];
  const older = [message('a', 99), message('b', 0), message('c', 1)];
  expect(mergeOlderChatHistory(current, older).map(item => item.id)).toEqual([
    'a',
    'b',
    'c',
    'd',
  ]);
  expect(
    mergeOlderChatHistory(mergeOlderChatHistory(current, older), older).map(
      item => item.id,
    ),
  ).toEqual(['a', 'b', 'c', 'd']);
});

test('canonical history replaces matching local echoes and retains pending rows', () => {
  const local = [
    {
      id: 'same',
      text: 'local',
      sender: 'human' as const,
      createdAt: 1,
      generationOutcome: null,
    },
    {
      id: 'pending',
      text: 'pending',
      sender: 'human' as const,
      createdAt: 2,
      generationOutcome: null,
    },
  ];
  const canonical = [
    {
      id: 'same',
      text: 'canonical',
      sender: 'human' as const,
      createdAt: 1,
      generationOutcome: null,
    },
  ];
  expect(reconcileCanonicalChatHistory(local, canonical)).toEqual([
    canonical[0],
    local[1],
  ]);
});
