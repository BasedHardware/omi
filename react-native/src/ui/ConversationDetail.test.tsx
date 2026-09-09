import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import type {ConversationProjection} from '../desktopReadClient';

const mockRecording = jest.fn(() => ({
  result: {
    status: 'loaded',
    value: {
      state: 'completed',
      text: 'Canonical transcript',
      discardedLeadingPackets: 0,
    },
  },
  reload: jest.fn(),
}));
const mockChat = jest.fn(() => ({
  result: {
    status: 'loaded',
    messages: [{id: 'm', sender: 'human', text: 'Named chat message'}],
    hasOlder: false,
    olderCursor: null,
  },
  reload: jest.fn(),
  loadingOlder: false,
  loadOlder: jest.fn(),
  olderNotice: null,
  olderRetryable: true,
}));
const mockLegacy = jest.fn();
jest.mock('../recordingTranscript', () => ({
  useRecordingTranscript: (...args: unknown[]) =>
    mockRecording(...(args as [])),
}));
jest.mock('../chatConversationHistory', () => ({
  MAIN_CHAT_CONVERSATION_ID: 'chat:chat-main',
  useChatConversationHistory: (...args: unknown[]) => mockChat(...args),
}));
jest.mock('../useLegacyConversationDetail', () => ({
  useLegacyConversationDetail: (...args: unknown[]) => mockLegacy(...args),
}));
const {ConversationDetail} = require('./ConversationDetail');
const conversation: ConversationProjection = {
  kind: 'conversation',
  id: 'recording:session-1',
  title: 'Planning',
  summary: 'Summary',
  searchableText: '',
  createdAt: '2026-09-09T00:00:00Z',
  updatedAt: null,
  startedAt: null,
  finishedAt: null,
  starred: false,
  status: 'completed',
  source: 'omi',
  visibility: 'private',
  folderId: null,
  locked: false,
  discarded: false,
};
const mounted: Renderer.ReactTestRenderer[] = [];
function render(props: Record<string, unknown> = {}) {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <ConversationDetail conversation={conversation} {...props} />,
    );
  });
  mounted.push(view);
  return view;
}
function text(view: Renderer.ReactTestRenderer) {
  return view.root
    .findAllByType(Text)
    .flatMap(node => node.props.children)
    .join(' ');
}
beforeEach(() => jest.clearAllMocks());
afterEach(() => act(() => mounted.splice(0).forEach(view => view.unmount())));

test('canonical recording and named chat reuse their existing detail readers', () => {
  const recording = render({desktop: true});
  expect(mockRecording).toHaveBeenCalledWith('session-1', undefined);
  expect(text(recording)).toContain('Canonical transcript');
  const chat = render({
    conversation: {
      ...conversation,
      id: 'chat:named-session',
      source: 'chat',
      title: 'Saved prompt',
    },
  });
  expect(mockChat).toHaveBeenCalledWith(true, 'chat:named-session');
  expect(text(chat)).toContain('Named chat message');
  expect(mockLegacy).not.toHaveBeenCalled();
});

test('canonical listen rows do not invent a transcript producer', () => {
  const view = render({
    conversation: {...conversation, id: 'listen:one', source: 'listen'},
  });
  expect(mockRecording).not.toHaveBeenCalled();
  expect(text(view)).toContain(
    'A full transcript is not available for this conversation yet.',
  );
});

test('legacy details load the old-backend producer instead of claiming no transcript', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: false,
        sections: [{heading: 'Notes', bodyMarkdown: 'Full notes'}],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Full speech',
              speaker: 'SPEAKER_00',
              isUser: true,
              start: 0,
              end: 1,
            },
          ],
        },
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1', source: 'omi'},
  });
  expect(mockLegacy).toHaveBeenCalledWith('old-1', null);
  expect(mockRecording).not.toHaveBeenCalled();
  expect(text(view)).toContain('Full notes');
  expect(text(view)).toContain('You');
  expect(text(view)).toContain('Full speech');
  expect(text(view)).not.toContain(
    'A full transcript is not available for this conversation yet.',
  );
});

test('legacy empty unlocked transcripts stay empty instead of unavailable', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: false,
        sections: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  expect(
    text(
      render({
        apiContract: 'omi',
        conversation: {...conversation, id: 'old-1'},
      }),
    ),
  ).toContain('The transcript is empty.');
});

test('legacy NEXT LINE-only segments stay empty instead of blank speaker lines', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: false,
        sections: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: '\u0085',
              speaker: '\u0085',
              isUser: false,
              start: 0,
              end: 1,
            },
          ],
        },
      },
    },
    reload: jest.fn(),
  });
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(copy).toContain('The transcript is empty.');
  expect(copy).not.toContain('\u0085');
  expect(copy).not.toContain('Speaker');
});

test('legacy NEXT LINE-prefixed segments keep later speech', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: false,
        sections: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: '\u0085Recorded words',
              speaker: '\u0085SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1,
            },
          ],
        },
      },
    },
    reload: jest.fn(),
  });
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(copy).toContain('Recorded words');
  expect(copy).toContain('Speaker 1');
  expect(copy).not.toContain('\u0085');
  expect(copy).not.toContain('The transcript is empty.');
});

test('legacy load failure offers retry without inventing an empty transcript', () => {
  const reload = jest.fn();
  mockLegacy.mockReturnValue({
    result: {
      status: 'error',
      conversationId: 'old-1',
      error: 'Conversation details could not be loaded. Try again.',
    },
    reload,
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(view)).toContain('Conversation details could not be loaded.');
  expect(text(view)).not.toContain('The transcript is empty.');
  act(() =>
    view.root
      .find(
        node => node.props.accessibilityLabel === 'Retry conversation details',
      )
      .props.onPress(),
  );
  expect(reload).toHaveBeenCalledTimes(1);
});

test('conversation details name starred conversations without an empty star toggle', () => {
  const starred = render({
    conversation: {...conversation, starred: true},
  });
  expect(text(starred)).toContain('Starred');
  expect(
    starred.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Starred conversation' &&
        node.props.children === 'Starred',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    starred.root.findAll(
      node => node.props.accessibilityLabel === 'Not starred',
    ),
  ).toHaveLength(0);

  const unstarred = render();
  expect(text(unstarred)).not.toContain('Starred');
  expect(
    unstarred.root.findAll(
      node => node.props.accessibilityLabel === 'Not starred',
    ),
  ).toHaveLength(0);
});

test('legacy conversation details name starred conversations from the list row', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: false,
        sections: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const starred = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1', starred: true},
  });
  expect(text(starred)).toContain('Starred');
  expect(
    starred.root.findAll(
      node => node.props.accessibilityLabel === 'Starred conversation',
    ).length,
  ).toBeGreaterThan(0);
});
