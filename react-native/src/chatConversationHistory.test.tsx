import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import type {NativeHttpResponse} from './omiNativeTypes';
import type {
  ConversationProjection,
  DomainReadOutcome,
} from './desktopReadClient';
import {ChatBackendError} from './chatClient';

const mockRequest = jest.fn();
let mockInvalidated: (() => void) | undefined;
jest.mock('./omiNative', () => ({
  omiBackend: {request: (request: unknown) => mockRequest(request)},
  subscribeOmiBackendSessionInvalidated: (listener: () => void) => {
    mockInvalidated = listener;
    return () => {
      mockInvalidated = undefined;
    };
  },
}));

const {ConversationsPage} = require('./pages/Conversations');
const {MAIN_CHAT_CONVERSATION_ID} = require('./chatConversationHistory');

function historyResponse(
  messages: Array<{
    id: string;
    text: string;
    sender: 'human' | 'ai' | 'unknown';
    createdAt?: number;
    generationOutcome?: 'completed' | 'cancelled' | null;
    attachments?: Array<{
      id: string;
      displayName: string;
      mediaType: string;
      sizeBytes: number;
      contentReference: string | null;
    }>;
  }>,
  page: {olderCursor: string | null; hasOlder: boolean} = {
    olderCursor: null,
    hasOlder: false,
  },
): NativeHttpResponse {
  return {
    id: 'chat-history',
    status: 200,
    body: JSON.stringify({
      messages: messages.map(message => ({
        ...message,
        createdAt: message.createdAt ?? Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome:
          message.generationOutcome ??
          (message.sender === 'ai' ? 'completed' : null),
        type: 'text',
        updatedAt: message.createdAt ?? Date.parse('2026-09-07T12:00:00.000Z'),
        chatSessionId: null,
        appId: null,
        journalRevision: 1,
        payloadHash: 'sha256:test',
        messageSource: 'desktop_chat',
        rating: null,
        reported: false,
        revision: '1',
        attachments: message.attachments ?? [],
      })),
      page,
      capabilities: {
        maxAttachmentsPerMessage: 4,
        maxAttachmentBytes: 52_428_800,
        allowedAttachmentMimeTypes: ['text/plain'],
      },
    }),
  };
}

function textOf(renderer: ReactTestRenderer.ReactTestRenderer) {
  return renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
}

function conversation(
  overrides: Partial<ConversationProjection>,
): ConversationProjection {
  return {
    kind: 'conversation',
    id: MAIN_CHAT_CONVERSATION_ID,
    title: 'saved prompt',
    summary: 'saved prompt',
    searchableText: 'saved prompt',
    createdAt: '2026-09-07T00:00:00Z',
    updatedAt: '2026-09-07T00:01:00Z',
    startedAt: '2026-09-07T00:00:00Z',
    finishedAt: null,
    starred: false,
    status: 'in_progress',
    source: 'chat',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
    ...overrides,
  };
}

function outcome(
  items: ConversationProjection[],
): DomainReadOutcome<ConversationProjection> {
  return {
    status: 'success',
    value: {
      items,
      page: {
        windowStatus: 'complete',
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete',
        reasons: [],
      },
    },
  };
}

const renderers: ReactTestRenderer.ReactTestRenderer[] = [];

afterEach(() => {
  act(() => renderers.splice(0).forEach(renderer => renderer.unmount()));
  mockRequest.mockReset();
});

async function renderPage(items: ConversationProjection[]) {
  const native = require('react-native');
  jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage outcome={outcome(items)} loading={false} embedded />,
    );
  });
  renderers.push(renderer);
  return renderer;
}

test('opens chat:chat-main into persisted messages instead of a title-only detail', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {id: 'human-1', text: 'saved prompt', sender: 'human'},
      {id: 'ai-1', text: 'saved answer', sender: 'ai'},
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  expect(mockRequest).not.toHaveBeenCalled();
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(mockRequest).toHaveBeenCalledWith({
    id: 'chat-history',
    method: 'GET',
    expectedApiContract: 'canonical',
    path: '/v1/chat-messages?limit=50',
  });
  expect(textOf(renderer)).toContain('You · saved prompt');
  expect(textOf(renderer)).toContain('Omi · saved answer');
});

test('does not load main chat history for another chat session id', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {id: 'human-alpha', text: 'other session', sender: 'human'},
    ]),
  );
  const renderer = await renderPage([
    conversation({id: 'chat:session-alpha', title: 'Other session'}),
  ]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation Other session',
      )[0]!
      .props.onPress(),
  );
  expect(mockRequest).toHaveBeenCalledWith({
    id: 'chat-history',
    method: 'GET',
    expectedApiContract: 'canonical',
    path: '/v1/chat-messages?limit=50&chatSessionId=session-alpha',
  });
  expect(textOf(renderer)).toContain('You · other session');
  expect(textOf(renderer)).not.toContain(
    'Chat history for this conversation is not available here.',
  );
});

test('shows typed chat grant denial instead of an empty message list', async () => {
  mockRequest.mockRejectedValue(
    new ChatBackendError(403, 'forbidden', false, 'none', null),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('Chat is not available for this account.');
  expect(textOf(renderer)).toContain('Check again');
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(textOf(renderer)).not.toContain('You ·');
});

test('native unsupported chat history does not claim a connection blip', async () => {
  mockRequest.mockRejectedValue(
    Object.assign(new Error('unsupported'), {
      code: 'OMI_DEV_BACKEND_UNSUPPORTED',
    }),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain(
    'Chat history is not available on this backend yet.',
  );
  expect(textOf(renderer)).not.toContain(
    'Chat history could not be loaded. Check your connection and try again.',
  );
  expect(textOf(renderer)).not.toContain('Check again');
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Reload chat messages',
    ),
  ).toHaveLength(0);
});

test('nested non-retryable chat history 503s do not offer Check again', async () => {
  mockRequest.mockRejectedValue(
    new ChatBackendError(
      503,
      'development_backend_unsupported',
      false,
      'none',
      null,
    ),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain(
    'Chat history is not available on this backend yet.',
  );
  expect(textOf(renderer)).not.toContain('Check again');
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Reload chat messages',
    ),
  ).toHaveLength(0);
});

test('keeps an honest empty chat page instead of inventing a completed answer', async () => {
  mockRequest.mockResolvedValue(historyResponse([]));
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('No messages in this chat yet.');
  expect(textOf(renderer)).not.toContain('You ·');
  expect(textOf(renderer)).not.toContain('Omi ·');
});

test('an empty chat page with older history does not claim the chat is empty', async () => {
  mockRequest
    .mockResolvedValueOnce(
      historyResponse([], {olderCursor: 'older-1', hasOlder: true}),
    )
    .mockResolvedValueOnce(
      historyResponse(
        [{id: 'human-1', text: 'older prompt', sender: 'human'}],
        {
          olderCursor: null,
          hasOlder: false,
        },
      ),
    );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ).length,
  ).toBeGreaterThan(0);
  expect(textOf(renderer)).toContain('Load older messages');
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Load older messages',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · older prompt');
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
});

test('an empty chat page with an empty older cursor does not claim the chat is empty', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([], {olderCursor: '', hasOlder: true}),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
});

test('keeps loaded chat rows when olderCursor is empty instead of offering Load older', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([{id: 'human-2', text: 'newer prompt', sender: 'human'}], {
      olderCursor: '',
      hasOlder: true,
    }),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · newer prompt');
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
});

test('loads older main-chat pages instead of dropping persisted history', async () => {
  mockRequest
    .mockResolvedValueOnce(
      historyResponse(
        [{id: 'human-2', text: 'newer prompt', sender: 'human'}],
        {
          olderCursor: 'older-1',
          hasOlder: true,
        },
      ),
    )
    .mockResolvedValueOnce(
      historyResponse(
        [{id: 'human-1', text: 'older prompt', sender: 'human'}],
        {olderCursor: null, hasOlder: false},
      ),
    );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · newer prompt');
  expect(textOf(renderer)).not.toContain('You · older prompt');
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Load older messages',
      )[0]!
      .props.onPress(),
  );
  expect(mockRequest).toHaveBeenNthCalledWith(2, {
    id: 'chat-history',
    method: 'GET',
    expectedApiContract: 'canonical',
    path: '/v1/chat-messages?limit=50&olderCursor=older-1',
  });
  expect(textOf(renderer)).toContain('You · older prompt');
  expect(textOf(renderer)).toContain('You · newer prompt');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
});

test('loads older pages for a named chat session without mixing main history', async () => {
  mockRequest
    .mockResolvedValueOnce(
      historyResponse([{id: 'human-2', text: 'newer named', sender: 'human'}], {
        olderCursor: 'older-named',
        hasOlder: true,
      }),
    )
    .mockResolvedValueOnce(
      historyResponse([{id: 'human-1', text: 'older named', sender: 'human'}], {
        olderCursor: null,
        hasOlder: false,
      }),
    );
  const renderer = await renderPage([
    conversation({id: 'chat:session-alpha', title: 'Other session'}),
  ]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation Other session',
      )[0]!
      .props.onPress(),
  );
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Load older messages',
      )[0]!
      .props.onPress(),
  );
  expect(mockRequest).toHaveBeenNthCalledWith(2, {
    id: 'chat-history',
    method: 'GET',
    expectedApiContract: 'canonical',
    path: '/v1/chat-messages?limit=50&olderCursor=older-named&chatSessionId=session-alpha',
  });
  expect(textOf(renderer)).toContain('You · older named');
  expect(textOf(renderer)).toContain('You · newer named');
});

test('generic later-page chat history failures keep loaded messages', async () => {
  mockRequest
    .mockResolvedValueOnce(
      historyResponse(
        [{id: 'human-2', text: 'newer prompt', sender: 'human'}],
        {olderCursor: 'older-1', hasOlder: true},
      ),
    )
    .mockRejectedValueOnce(new Error('older page failed'));
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Load older messages',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · newer prompt');
  expect(textOf(renderer)).toContain(
    'Chat history could not be loaded. Check your connection and try again.',
  );
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Reload chat messages',
    ),
  ).toHaveLength(0);
});

test('nested non-retryable later chat history pages keep loaded messages', async () => {
  mockRequest
    .mockResolvedValueOnce(
      historyResponse(
        [{id: 'human-2', text: 'newer prompt', sender: 'human'}],
        {olderCursor: 'older-1', hasOlder: true},
      ),
    )
    .mockRejectedValueOnce(
      new ChatBackendError(
        503,
        'development_backend_unsupported',
        false,
        'none',
        null,
      ),
    );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Load older messages',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · newer prompt');
  expect(textOf(renderer)).toContain(
    'Chat history is not available on this backend yet.',
  );
  expect(textOf(renderer)).not.toContain(
    'Chat history could not be loaded. Check your connection and try again.',
  );
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Reload chat messages',
    ),
  ).toHaveLength(0);
});

test('an undecodable older chat cursor refreshes newest history instead of dead-ending', async () => {
  mockRequest
    .mockResolvedValueOnce(
      historyResponse(
        [{id: 'human-2', text: 'newer prompt', sender: 'human'}],
        {olderCursor: 'older-1', hasOlder: true},
      ),
    )
    .mockResolvedValueOnce({
      id: 'chat-history',
      status: 400,
      body: JSON.stringify({
        error: {
          code: 'bad_request',
          retryable: false,
          action: 'refresh_history',
        },
      }),
    })
    .mockResolvedValueOnce(
      historyResponse(
        [
          {id: 'human-1', text: 'older prompt', sender: 'human'},
          {id: 'human-2', text: 'newer prompt', sender: 'human'},
        ],
        {olderCursor: null, hasOlder: false},
      ),
    );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · newer prompt');
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Load older messages',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · older prompt');
  expect(textOf(renderer)).toContain('You · newer prompt');
  expect(textOf(renderer)).not.toContain(
    'Chat history is not available on this backend yet.',
  );
  expect(textOf(renderer)).not.toContain(
    'Chat history could not be loaded. Check your connection and try again.',
  );
  expect(mockRequest).toHaveBeenNthCalledWith(2, {
    id: 'chat-history',
    method: 'GET',
    expectedApiContract: 'canonical',
    path: '/v1/chat-messages?limit=50&olderCursor=older-1',
  });
  expect(mockRequest).toHaveBeenNthCalledWith(3, {
    id: 'chat-history',
    method: 'GET',
    expectedApiContract: 'canonical',
    path: '/v1/chat-messages?limit=50',
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
});

test('an empty chat page with a blocked older cursor does not claim the chat is empty', async () => {
  mockRequest
    .mockResolvedValueOnce(
      historyResponse([], {olderCursor: 'older-1', hasOlder: true}),
    )
    .mockRejectedValueOnce(
      new ChatBackendError(
        503,
        'development_backend_unsupported',
        false,
        'none',
        null,
      ),
    );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Load older messages',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain(
    'Chat history is not available on this backend yet.',
  );
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
});

test('a zero conversation-detail chat timestamp says Time unavailable instead of 1970', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'human-undated',
        text: 'undated prompt',
        sender: 'human',
        createdAt: 0,
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · undated prompt');
  expect(textOf(renderer)).toContain('Time unavailable');
  expect(textOf(renderer)).not.toContain('1970');
});

test('a cancelled conversation-detail chat message says Response stopped instead of a completed blank answer', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'human-stopped',
        text: 'stopped prompt',
        sender: 'human',
      },
      {
        id: 'ai-stopped',
        text: '',
        sender: 'ai',
        generationOutcome: 'cancelled',
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · stopped prompt');
  expect(textOf(renderer)).toContain('Omi · Response stopped');
});

test('a cancelled whitespace-only conversation-detail chat message says Response stopped instead of a blank answer', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'ai-whitespace-stopped',
        text: ' \t\n',
        sender: 'ai',
        generationOutcome: 'cancelled',
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('Omi · Response stopped');
  expect(textOf(renderer)).not.toContain('Omi ·  \t\n');
});

test('a cancelled NEXT LINE-only conversation-detail chat message says Response stopped instead of a blank answer', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'ai-next-line-stopped',
        text: '\u0085',
        sender: 'ai',
        generationOutcome: 'cancelled',
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('Omi · Response stopped');
  expect(textOf(renderer)).not.toContain('\u0085');
  expect(
    renderer.root.findAll(node => node.props.children === 'Response stopped'),
  ).toHaveLength(0);
});

test('a whitespace-only conversation-detail chat message says Message text unavailable instead of a blank answer', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'human-whitespace',
        text: ' \t\n',
        sender: 'human',
        generationOutcome: null,
      },
      {
        id: 'ai-whitespace',
        text: ' \t\n',
        sender: 'ai',
        generationOutcome: 'completed',
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · Message text unavailable');
  expect(textOf(renderer)).toContain('Omi · Message text unavailable');
  expect(textOf(renderer)).not.toContain('Response stopped');
});

test('conversation-detail history keeps attachment names on empty message text', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'human-attachment',
        text: ' \t\n',
        sender: 'human',
        generationOutcome: null,
        attachments: [
          {
            id: 'att-notes',
            displayName: 'notes.txt',
            mediaType: 'text/plain',
            sizeBytes: 12,
            contentReference: null,
          },
        ],
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · notes.txt · Text · 12 B');
  expect(textOf(renderer)).not.toContain('You · Message text unavailable');
});

test('an unknown conversation-detail chat sender stays visible instead of hiding the thread', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'human-known',
        text: 'saved prompt',
        sender: 'human',
        generationOutcome: null,
      },
      {
        id: 'unknown-sender',
        text: 'unlabeled',
        sender: 'unknown',
        generationOutcome: null,
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('You · saved prompt');
  expect(textOf(renderer)).toContain('Sender unavailable · unlabeled');
  expect(textOf(renderer)).not.toContain('Omi · unlabeled');
});

test('a cancelled conversation-detail chat message with text still says Response stopped', async () => {
  mockRequest.mockResolvedValue(
    historyResponse([
      {
        id: 'ai-partial',
        text: 'partial answer',
        sender: 'ai',
        generationOutcome: 'cancelled',
      },
    ]),
  );
  const renderer = await renderPage([conversation({})]);
  await act(async () =>
    renderer.root
      .findAll(
        node =>
          node.props.accessibilityLabel === 'Open conversation saved prompt',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('Omi · partial answer');
  expect(textOf(renderer)).toContain('Response stopped');
});
