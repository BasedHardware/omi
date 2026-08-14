import {
  loadChatHistory,
  parseTerminal,
  sendChatMessage,
} from '../src/chatClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNative';

test('loads main Chat history through the native boundary', async () => {
  const requests: NativeHttpRequest[] = [];
  const backend = {
    request: async (request: NativeHttpRequest) => {
      requests.push(request);
      return {id: request.id, status: 200, body: '{"messages":[]}'};
    },
    generationEvents: async () => '',
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
      return `event: snapshot\nid: e1\ndata: {"kind":"snapshot","text":"H"}\n\nevent: done\nid: e2\ndata: ${JSON.stringify(
        {kind: 'done', message: assistant},
      )}\n\n`;
    },
    cancelGenerationEvents: async () => {},
  } satisfies OmiBackend;

  await expect(sendChatMessage(backend, 'Hello', 100)).resolves.toEqual({
    human,
    assistant,
  });
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
