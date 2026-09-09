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
jest.mock('./omiNative', () => ({
  omiBackend: {request: (request: unknown) => mockRequest(request)},
  subscribeOmiBackendSessionInvalidated: () => () => {},
}));

const {ConversationsPage} = require('./pages/Conversations');
const {MAIN_CHAT_CONVERSATION_ID} = require('./chatConversationHistory');

function historyResponse(
  messages: Array<{id: string; text: string; sender: 'human' | 'ai'}>,
): NativeHttpResponse {
  return {
    id: 'chat-history',
    status: 200,
    body: JSON.stringify({
      messages: messages.map(message => ({
        ...message,
        createdAt: 1_000,
        generationOutcome: message.sender === 'ai' ? 'completed' : null,
        type: 'text',
        updatedAt: 1_000,
        chatSessionId: null,
        appId: null,
        journalRevision: 1,
        payloadHash: 'sha256:test',
        messageSource: 'desktop_chat',
        rating: null,
        reported: false,
        revision: '1',
        attachments: [],
      })),
      page: {olderCursor: null, hasOlder: false},
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
  expect(mockRequest).not.toHaveBeenCalled();
  expect(textOf(renderer)).toContain(
    'Chat history for this conversation is not available here.',
  );
  expect(textOf(renderer)).not.toContain('You ·');
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
  expect(textOf(renderer)).not.toContain('No messages in this chat yet.');
  expect(textOf(renderer)).not.toContain('You ·');
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
