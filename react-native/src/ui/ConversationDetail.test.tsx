import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import type {ConversationProjection} from '../desktopReadClient';
import {MAIN_CHAT_CONVERSATION_ID} from '../chatConversationHistory';

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
    messages: [{id: 'm', sender: 'human', text: 'Main chat message'}],
  },
  reload: jest.fn(),
}));
const mockLegacy = jest.fn();
jest.mock('../recordingTranscript', () => ({
  useRecordingTranscript: (...args: unknown[]) =>
    mockRecording(...(args as [])),
}));
jest.mock('../chatConversationHistory', () => ({
  MAIN_CHAT_CONVERSATION_ID: 'main-chat',
  useChatConversationHistory: (...args: unknown[]) => mockChat(...(args as [])),
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

test('canonical recording and main chat reuse their existing detail readers', () => {
  const recording = render({desktop: true});
  expect(mockRecording).toHaveBeenCalledWith('session-1', undefined);
  expect(text(recording)).toContain('Canonical transcript');
  const chat = render({
    conversation: {
      ...conversation,
      id: MAIN_CHAT_CONVERSATION_ID,
      source: 'chat',
    },
  });
  expect(mockChat).toHaveBeenCalledWith(true);
  expect(text(chat)).toContain('Main chat message');
  expect(mockLegacy).not.toHaveBeenCalled();
});

test('unknown canonical chat does not load unrelated main messages', () => {
  const view = render({
    conversation: {...conversation, id: 'other-chat', source: 'chat'},
  });
  expect(text(view)).toContain(
    'Chat history for this conversation is not available here.',
  );
  expect(mockChat).not.toHaveBeenCalled();
});

test('legacy contract renders real detail sections and speaker transcript without canonical requests', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      value: {
        id: conversation.id,
        title: 'Loaded title',
        summary: 'Loaded summary',
        locked: false,
        sections: [{heading: 'Decisions', bodyMarkdown: 'Ship the feature'}],
        transcript: {
          status: 'loaded',
          segments: [
            {text: 'Agreed', speaker: 'Sam', isUser: false, start: 0, end: 1},
          ],
        },
      },
    },
    reload: jest.fn(),
  });
  const view = render({apiContract: 'omi', desktop: true});
  expect(mockLegacy).toHaveBeenCalledWith(conversation.id, null);
  expect(text(view)).toContain('Loaded title');
  expect(text(view)).toContain('Decisions');
  expect(text(view)).toContain('Ship the feature');
  expect(text(view)).toContain('Sam');
  expect(text(view)).toContain('Agreed');
  expect(mockRecording).not.toHaveBeenCalled();
});

test('legacy loading, failure retry and unavailable transcript remain honest', () => {
  const reload = jest.fn();
  mockLegacy.mockReturnValue({result: {status: 'loading'}, reload});
  expect(text(render({apiContract: 'omi'}))).toContain('Loading conversation…');
  mockLegacy.mockReturnValue({
    result: {
      status: 'error',
      error: 'Sign in again to read this conversation.',
    },
    reload,
  });
  const error = render({apiContract: 'omi'});
  expect(text(error)).not.toContain('Summary');
  act(() =>
    error.root
      .findAll(
        node => node.props.accessibilityLabel === 'Retry conversation details',
      )[0]!
      .props.onPress(),
  );
  expect(reload).toHaveBeenCalledTimes(1);
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      value: {
        id: conversation.id,
        title: 'Locked',
        summary: '',
        locked: true,
        sections: [],
        transcript: {status: 'unavailable'},
      },
    },
    reload,
  });
  const locked = render({apiContract: 'omi'});
  expect(text(locked)).toContain(
    'This conversation is locked. Transcript unavailable.',
  );
  expect(text(locked)).not.toContain('The transcript is empty.');
});

test('transcript formats numbered speakers, preserves names, and labels the user You', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      value: {
        id: conversation.id,
        title: 'Conversation',
        summary: '',
        locked: false,
        sections: [],
        transcript: {
          status: 'loaded',
          segments: [
            {text: 'First', speaker: 'SPEAKER_00', isUser: false},
            {text: 'Second', speaker: 'SPEAKER_01', isUser: false},
            {text: 'Named', speaker: 'Sam', isUser: false},
            {text: 'Mine', speaker: 'SPEAKER_02', isUser: true},
          ],
        },
      },
    },
    reload: jest.fn(),
  });
  const view = render({apiContract: 'omi'});
  expect(text(view)).toContain('Speaker 1');
  expect(text(view)).toContain('Speaker 2');
  expect(text(view)).toContain('Sam');
  expect(text(view)).toContain('You');
  expect(text(view)).not.toContain('SPEAKER_');
});
