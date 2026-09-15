import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Linking, Text} from 'react-native';
import type {ConversationProjection} from '../desktopReadClient';
import {
  clockLabel,
  conversationDetailDateChipCopy,
  chatBlockUnavailableCopy,
  chatBlockLoadingCopy,
  chatDiscoveryShowMoreCopy,
  chatDiscoveryShowLessCopy,
  desktopBackendServiceCopy,
  conversationFirstPartySummaryCopy,
  conversationNoSummaryCopy,
  conversationNoSummaryForAppCopy,
  processingConversationNoContentCopy,
  processingConversationNoSummaryCopy,
  processingConversationStatusCopy,
  processingConversationDetailTitleCopy,
  processingConversationDetailContentTabCopy,
  conversationActionItemsTodoCopy,
  conversationActionItemsNoPendingCopy,
  conversationActionItemsCompletedCopy,
  conversationActionItemsNoCompletedCopy,
  conversationActionItemsEmptyCopy,
  conversationActionItemsEmptyDescriptionCopy,
  conversationNoFolderCopy,
  conversationUnknownAppCopy,
  conversationUnknownLocationCopy,
  conversationPhotoUnavailableCopy,
  transcriptSttUnknownCopy,
  transcriptSttOmiFallbackCopy,
} from '../desktopReadClient';

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

test('conversation-detail history names unanswered GET questionCard option labels', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-question',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [
            {
              eyebrow: 'Question',
              title: 'Schedule the follow-up?',
              detail: 'Yes, schedule it · Not now',
            },
          ],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const copy = text(
    render({
      conversation: {
        ...conversation,
        id: 'chat:chat-main',
        source: 'chat',
        title: 'Main chat',
      },
    }),
  );
  expect(copy).toContain('Question');
  expect(copy).toContain('Schedule the follow-up?');
  expect(copy).toContain('Yes, schedule it · Not now');
  expect(copy).not.toContain('preparedAnswer');
  expect(copy).not.toContain('Open in Goals');
});

test('conversation-detail history names GET followUp text without send chips', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-follow',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [{eyebrow: 'Want me to draft the recap next?'}],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const copy = text(view);
  expect(copy).toContain('Want me to draft the recap next?');
  expect(copy).toContain('Here is what I found.');
  expect(copy).not.toContain('preparedAnswer');
  expect(copy).not.toContain('Open in Goals');
  expect(
    view.root.findAll(
      node =>
        node.props.accessibilityRole === 'button' &&
        String(node.props.accessibilityLabel ?? '').includes(
          'Want me to draft the recap next?',
        ),
    ),
  ).toHaveLength(0);
});

test('conversation-detail history names GET memory citations with empty titles', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-empty-cited',
          sender: 'ai',
          text: 'I found that meeting.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          memories: [
            {title: '', emoji: '🧠'},
            {title: '  '},
            {title: '\u0085', emoji: '🚀'},
          ],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const tree = text(view);
  expect(tree).toContain('I found that meeting.');
  expect(tree).toContain('🧠 ');
  expect(tree).toContain('🚀 \u0085');
});

test('conversation-detail history names Flutter ChartMessageWidget empty GET title without omitting the chart', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-empty-chart-title',
          sender: 'ai',
          text: 'Here is the trend.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          chart: {
            title: '',
            points: [
              {label: 'Mon', value: 12},
              {label: ' \t', value: 1},
            ],
          },
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loading: false,
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const tree = text(view);
  expect(tree).toContain('Here is the trend.');
  expect(tree).toContain('\nMon · 12\n \t · 1');
  expect(tree).not.toContain('Here is the trend.\nMon · 12');
});

test('conversation-detail history names GET content_blocks without inventing write actions', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-1',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          appName: 'Notes',
          appImage: 'https://cdn.example.test/notes.png',
          memories: [{title: 'Morning standup', emoji: '🚀'}],
          evidence: [{title: 'Calendar', detail: 'Tuesday agenda'}],
          contentBlocks: [
            {
              eyebrow: 'Discovery',
              title: 'Quiet mornings',
              detail: 'You like a slow start.',
            },
            {eyebrow: 'Memory', title: 'Prefers concise notes'},
            {eyebrow: 'Task'},
          ],
        },
        {
          id: 'human-1',
          sender: 'human',
          text: 'Save this.',
          createdAt: Date.parse('2026-09-07T12:01:00.000Z'),
          generationOutcome: null,
          appName: 'Notes',
          appImage: 'https://cdn.example.test/notes.png',
          contentBlocks: [{eyebrow: 'Discovery', title: 'Quiet mornings'}],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const tree = text(view);
  expect(tree).toContain('Here is what I found.');
  expect(tree).toContain('Notes');
  expect(tree).toContain('🚀 Morning standup');
  expect(tree).toContain('Calendar');
  expect(tree).toContain('Tuesday agenda');
  expect(tree).toContain('Discovery');
  expect(tree).toContain('Quiet mornings');
  expect(tree).toContain('You like a slow start.');
  expect(tree).toContain('Prefers concise notes');
  expect(tree).toContain('Task');
  expect(tree).toContain('Save this.');
  expect(tree).not.toContain('Open in Memories');
  expect(tree).not.toContain('Open conversation');
  expect(tree).not.toContain('Open in Goals');
  expect(tree).not.toContain('Show more');
  expect(
    view.root.findAll(
      node => node.props.source?.uri === 'https://cdn.example.test/notes.png',
    ).length,
  ).toBeGreaterThan(0);
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'human-only',
          sender: 'human',
          text: 'Save this.',
          createdAt: Date.parse('2026-09-07T12:01:00.000Z'),
          generationOutcome: null,
          appName: 'Notes',
          appImage: 'https://cdn.example.test/notes.png',
          contentBlocks: [{eyebrow: 'Discovery', title: 'Quiet mornings'}],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const human = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const humanTree = text(human);
  expect(humanTree).toContain('Save this.');
  expect(humanTree).not.toContain('Notes');
  expect(humanTree).not.toContain('Discovery');
  expect(humanTree).not.toContain('Quiet mornings');
  expect(
    human.root.findAll(
      node => node.props.source?.uri === 'https://cdn.example.test/notes.png',
    ),
  ).toHaveLength(0);
});

test('conversation-detail history names GET discovery fullText Show more without a write', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-1',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [
            {
              eyebrow: 'Discovery',
              title: 'Quiet mornings',
              detail: 'You like a slow start.',
              more: 'Longer body stays collapsed.',
            },
          ],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const tree = text(view);
  expect(tree).toContain('Discovery');
  expect(tree).toContain('You like a slow start.');
  expect(tree).toContain(chatDiscoveryShowMoreCopy());
  expect(tree).not.toContain('Longer body stays collapsed.');
  expect(tree).not.toContain(chatDiscoveryShowLessCopy());
  const more = view.root.find(
    node =>
      node.props.accessibilityLabel === chatDiscoveryShowMoreCopy() &&
      typeof node.props.onPress === 'function',
  );
  act(() => {
    more.props.onPress();
  });
  const expanded = text(view);
  expect(expanded).toContain('Longer body stays collapsed.');
  expect(expanded).toContain(chatDiscoveryShowLessCopy());
  expect(expanded).not.toContain(chatDiscoveryShowMoreCopy());
  expect(expanded).not.toContain('You like a slow start.');
});

test('conversation-detail history names loaded GET task_card description without leaking ids', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-1',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [{eyebrow: 'Task', taskId: 'task-join'}],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    tasks: [{id: 'task-join', title: 'Send the follow-up notes'}],
  });
  const tree = text(view);
  expect(tree).toContain('Task');
  expect(tree).toContain('Send the follow-up notes');
  expect(tree).not.toContain('task-join');
  expect(tree).not.toContain('Loading');
  expect(tree).not.toContain(chatBlockUnavailableCopy());
  const unmatched = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    tasks: [{id: 'other', title: 'Send the follow-up notes'}],
  });
  const unmatchedTree = text(unmatched);
  expect(unmatchedTree).toContain('Task');
  expect(unmatchedTree).toContain(chatBlockUnavailableCopy());
  expect(unmatchedTree).not.toContain('Send the follow-up notes');
  expect(unmatchedTree).not.toContain('task-join');
  expect(unmatchedTree).not.toContain('Loading');
  const unloaded = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const unloadedTree = text(unloaded);
  expect(unloadedTree).toContain('Task');
  expect(unloadedTree).toContain(chatBlockLoadingCopy());
  expect(unloadedTree).not.toContain(chatBlockUnavailableCopy());
});

test('conversation-detail history names Flutter TaskCardBlock empty GET descriptions', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-empty-task',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [{eyebrow: 'Task', taskId: 'task-join'}],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loading: false,
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    tasks: [{id: 'task-join', title: ''}],
  });
  expect(
    view.root.findAll(node => node.props.accessibilityLabel === 'Task: ')
      .length,
  ).toBeGreaterThan(0);
  const tree = text(view);
  expect(tree).toContain('Task');
  expect(tree).not.toContain(chatBlockUnavailableCopy());
  expect(tree).not.toContain(chatBlockLoadingCopy());
  expect(tree).not.toContain('task-join');
  const whitespace = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    tasks: [{id: 'task-join', title: ' \t'}],
  });
  expect(
    whitespace.root.findAll(
      node => node.props.accessibilityLabel === 'Task:  \t',
    ).length,
  ).toBeGreaterThan(0);
});

test('conversation-detail history names Flutter ChatBlockLinkCard padded GET summaries', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-padded-link',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [
            {eyebrow: 'Goal', title: '  padded  '},
            {
              eyebrow: 'Discovery',
              title: '  padded  ',
              detail: 'padded body',
            },
          ],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loading: false,
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Goal:   padded  ',
    ).length,
  ).toBeGreaterThan(0);
  const tree = text(view);
  expect(tree).toContain('  padded  ');
  expect(tree).toContain('padded body');
  expect(tree).not.toContain('Open in Goals');
});

test('conversation-detail history names Flutter HumanMessage padded GET text without colliding with trim', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'human-padded',
          sender: 'human',
          text: '  Hello  ',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: null,
        },
        {
          id: 'ai-padded',
          sender: 'ai',
          text: '  Hello  ',
          createdAt: Date.parse('2026-09-07T12:01:00.000Z'),
          generationOutcome: 'completed',
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loading: false,
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  expect(
    view.root.findAll(
      node =>
        String(node.type) === 'Text' &&
        node.props.children === 'You ·   Hello',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    view.root.findAll(
      node =>
        String(node.type) === 'Text' &&
        node.props.children === 'Omi ·   Hello',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    view.root.findAll(
      node =>
        String(node.type) === 'Text' &&
        node.props.children === 'You · Hello',
    ),
  ).toHaveLength(0);
  expect(
    view.root.findAll(
      node =>
        String(node.type) === 'Text' &&
        node.props.children === 'Omi · Hello',
    ),
  ).toHaveLength(0);
});

test('conversation-detail history names Flutter FilesHandlerWidget padded GET image thumbnails instead of remapping to a CDN chip', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'human-padded-photo',
          sender: 'human',
          text: 'Here is the photo.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: null,
          attachments: [
            {
              id: 'att-photo',
              displayName: 'photo.png',
              mediaType: 'image/png',
              thumbnail: 'https://cdn.example/photo.png',
            },
            {
              id: 'att-padded',
              displayName: 'padded.png',
              mediaType: 'image/png',
              thumbnail: '  https://cdn.example/photo.png  ',
            },
            {
              id: 'att-lead',
              displayName: 'lead.png',
              mediaType: 'image/png',
              thumbnail: ' http://cdn.example/photo.jpg ',
            },
            {
              id: 'att-trail',
              displayName: 'trail.png',
              mediaType: 'image/png',
              thumbnail: 'https://cdn.example/photo.png ',
            },
            {
              id: 'att-https',
              displayName: 'https.png',
              mediaType: 'image/png',
              thumbnail: 'HTTPS://cdn.example/photo.png',
            },
          ],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loading: false,
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const uris = view.root
    .findAll(node => String(node.type) === 'Image')
    .map(node => node.props.source?.uri)
    .filter(
      (uri): uri is string =>
        typeof uri === 'string' && uri.includes('cdn.example/photo'),
    );
  expect(uris).toEqual([
    'https://cdn.example/photo.png',
    'https://cdn.example/photo.png ',
    'HTTPS://cdn.example/photo.png',
  ]);
});

test('conversation-detail history names loaded GET goal_link miss No longer available without leaking ids', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-1',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [
            {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'goal-join'},
          ],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    goals: [{id: 'goal-join'}],
  });
  const tree = text(view);
  expect(tree).toContain('Goal');
  expect(tree).toContain('Ship the recap');
  expect(tree).not.toContain('goal-join');
  expect(tree).not.toContain('Loading');
  expect(tree).not.toContain(chatBlockUnavailableCopy());
  expect(tree).not.toContain('Open in Goals');
  const unmatched = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    goals: [{id: 'other'}],
  });
  const unmatchedTree = text(unmatched);
  expect(unmatchedTree).toContain('Goal');
  expect(unmatchedTree).toContain(chatBlockUnavailableCopy());
  expect(unmatchedTree).not.toContain('Ship the recap');
  expect(unmatchedTree).not.toContain('goal-join');
  expect(unmatchedTree).not.toContain('Loading');
  expect(unmatchedTree).not.toContain('Open in Goals');
  const unloaded = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const unloadedTree = text(unloaded);
  expect(unloadedTree).toContain('Goal');
  expect(unloadedTree).toContain('Ship the recap');
  expect(unloadedTree).not.toContain(chatBlockUnavailableCopy());
  expect(unloadedTree).not.toContain('Loading');
});

test('conversation-detail history names loaded GET memory_link miss No longer available without leaking ids', () => {
  mockChat.mockReturnValue({
    result: {
      status: 'loaded',
      messages: [
        {
          id: 'ai-1',
          sender: 'ai',
          text: 'Here is what I found.',
          createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
          generationOutcome: 'completed',
          contentBlocks: [
            {
              eyebrow: 'Memory',
              title: 'Prefers concise notes',
              memoryId: 'mem-join',
            },
          ],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    },
    reload: jest.fn(),
    loadingOlder: false,
    loadOlder: jest.fn(),
    olderNotice: null,
    olderRetryable: true,
  });
  const view = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    memories: [{id: 'mem-join'}],
  });
  const tree = text(view);
  expect(tree).toContain('Memory');
  expect(tree).toContain('Prefers concise notes');
  expect(tree).not.toContain('mem-join');
  expect(tree).not.toContain('Loading');
  expect(tree).not.toContain(chatBlockUnavailableCopy());
  expect(tree).not.toContain('Open in Memories');
  const unmatched = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
    memories: [{id: 'other'}],
  });
  const unmatchedTree = text(unmatched);
  expect(unmatchedTree).toContain('Memory');
  expect(unmatchedTree).toContain(chatBlockUnavailableCopy());
  expect(unmatchedTree).not.toContain('Prefers concise notes');
  expect(unmatchedTree).not.toContain('mem-join');
  expect(unmatchedTree).not.toContain('Loading');
  expect(unmatchedTree).not.toContain('Open in Memories');
  const unloaded = render({
    conversation: {
      ...conversation,
      id: 'chat:chat-main',
      source: 'chat',
      title: 'Main chat',
    },
  });
  const unloadedTree = text(unloaded);
  expect(unloadedTree).toContain('Memory');
  expect(unloadedTree).toContain('Prefers concise notes');
  expect(unloadedTree).not.toContain(chatBlockUnavailableCopy());
  expect(unloadedTree).not.toContain('Loading');
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

test('listen details omit Flutter GetSummaryWidgets unused invented overview', () => {
  const completed = text(
    render({
      conversation: {
        ...conversation,
        id: 'listen:empty-overview',
        source: 'listen',
        summary: '',
        status: 'completed',
      },
    }),
  );
  expect(completed).toContain('Planning');
  expect(completed).not.toContain('Conversation summary unavailable');
  expect(completed).not.toContain('Conversation summary is not ready yet.');
  expect(completed).toContain(
    'A full transcript is not available for this conversation yet.',
  );
  const processing = text(
    render({
      conversation: {
        ...conversation,
        id: 'listen:empty-overview-processing',
        source: 'listen',
        summary: ' \t\n',
        status: 'processing',
      },
    }),
  );
  expect(processing).toContain('Planning');
  expect(processing).not.toContain('Conversation summary is not ready yet.');
  expect(processing).not.toContain('Conversation summary unavailable');
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

test('legacy empty unlocked transcripts omit invented empty chrome instead of unavailable', () => {
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
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(copy).toContain('A real conversation');
  expect(copy).not.toContain('The transcript is empty.');
  expect(copy).not.toContain(processingConversationNoContentCopy());
  expect(copy).not.toContain('Transcript unavailable');
});

test('legacy processing empty GET transcript text names Flutter TranscriptWidget instead of noContentToDisplay', () => {
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
              text: ' \t\n',
              speaker: 'SPEAKER_00',
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
      conversation: {...conversation, id: 'old-1', status: 'processing'},
    }),
  );
  expect(copy).toContain('Speaker 1');
  expect(copy).toContain(' \t\n');
  expect(copy).not.toContain(processingConversationNoContentCopy());
  expect(copy).not.toContain('The transcript is empty.');
  expect(copy).not.toContain('Transcript unavailable');
});

test('legacy processing empty transcript names Flutter noContentToDisplay without photos', () => {
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
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', status: 'processing'},
    }),
  );
  expect(copy).toContain(processingConversationNoContentCopy());
  expect(copy).not.toContain('The transcript is empty.');
  expect(copy).not.toContain('Transcript unavailable');
});

test('legacy conversation details name Flutter TranscriptWidget empty GET text', () => {
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
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  const whitespaceText = view.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return (
      children === '\u0085' ||
      (Array.isArray(children) && children.some(child => child === '\u0085'))
    );
  });
  expect(whitespaceText.length).toBeGreaterThan(0);
  expect(copy).toContain('Speaker 1');
  expect(copy).not.toContain('The transcript is empty.');
  expect(copy).not.toContain(processingConversationNoContentCopy());
  expect(copy).toContain('\u0085');
  expect(copy).not.toContain('Speaker ·');
});

test('legacy conversation details name Flutter empty GET speakers', () => {
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
              text: 'Recorded words',
              speaker: ' \t\n',
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
  expect(copy).toContain('Speaker 1');
  expect(copy).toContain('Recorded words');
  expect(copy).not.toContain('Speaker ·');
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
  expect(copy).toContain('\u0085Recorded words');
  expect(copy).toContain('Speaker 1');
  expect(copy).not.toContain('\u0085SPEAKER_00');
  expect(copy).not.toContain('The transcript is empty.');
});

test('legacy transcript names GET start and end when segments do not overlap', () => {
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
              text: 'First words',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1.9,
            },
            {
              text: 'Later words',
              speaker: 'SPEAKER_01',
              isUser: false,
              start: 2,
              end: 5,
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
  expect(copy).toContain('Speaker 1');
  expect(copy).toContain('First words');
  expect(copy).toContain('00:00:00 - 00:00:01');
  expect(copy).toContain('Speaker 2');
  expect(copy).toContain('Later words');
  expect(copy).toContain('00:00:02 - 00:00:05');
});

test('legacy transcript omits GET clocks when segments overlap', () => {
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
              text: 'First words',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 3,
            },
            {
              text: 'Later words',
              speaker: 'SPEAKER_01',
              isUser: false,
              start: 1,
              end: 5,
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
  expect(copy).toContain('Speaker 1');
  expect(copy).toContain('First words');
  expect(copy).toContain('Speaker 2');
  expect(copy).toContain('Later words');
  expect(copy).not.toContain('00:00:00');
  expect(copy).not.toContain('00:00:01');
  expect(copy).not.toContain('00:00:03');
});

test('legacy NEXT LINE-prefixed sections keep later notes', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: false,
        sections: [{heading: '\u0085Notes', bodyMarkdown: '\u0085Full notes'}],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain('Notes');
  expect(copy).toContain('Full notes');
  expect(copy).not.toContain('\u0085');
});

test('legacy NEXT LINE-only sections stay omitted instead of blank notes', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: false,
        sections: [{heading: '\u0085', bodyMarkdown: '\u0085'}],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).not.toContain('\u0085');
  expect(copy).not.toContain('The transcript is empty.');
  expect(copy).not.toContain(processingConversationNoContentCopy());
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

test('an in-progress chat does not invent a Finished clock', () => {
  const copy = text(
    render({
      conversation: {
        ...conversation,
        id: 'chat:chat-main',
        source: 'chat',
        status: 'in_progress',
        startedAt: '2026-09-07T00:00:00.000Z',
        finishedAt: null,
      },
    }),
  );
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('In progress');
  expect(copy).not.toContain('Status ·');
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('Duration unavailable');
});

test('conversation details omit Flutter GetSummaryWidgets unused Starred chip', () => {
  const starred = render({
    conversation: {...conversation, starred: true},
  });
  expect(text(starred)).not.toContain('Starred');
  expect(
    starred.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Starred conversation' ||
        node.props.children === 'Starred',
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

test('legacy conversation details omit Flutter GetSummaryWidgets unused Starred chip', () => {
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
  expect(text(starred)).not.toContain('Starred');
  expect(
    starred.root.findAll(
      node => node.props.accessibilityLabel === 'Starred conversation',
    ),
  ).toHaveLength(0);
});

test('legacy conversation details keep GET clocks from the list row', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary',
        locked: true,
        sections: [],
        transcript: {status: 'unavailable'},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {
      ...conversation,
      id: 'old-1',
      startedAt: '2026-09-07T12:00:00.000Z',
      finishedAt: '2026-09-07T12:05:00.000Z',
      status: 'completed',
      discarded: true,
    },
  });
  const copy = text(view);
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('Duration unavailable');
  expect(copy).not.toContain('Status ·');
  expect(copy).not.toContain('Completed');
  expect(copy).not.toContain('Locked');
  expect(copy).toContain('This conversation is locked. Transcript unavailable.');
  expect(copy).toContain('Discarded Conversation');
  expect(
    view.root.findAll(node => node.props.children === 'Discarded'),
  ).toHaveLength(0);
  expect(copy).not.toContain('in_progress');
});

test('conversation details name Flutter GetSummaryWidgets date and time', () => {
  const older = new Date(2025, 7, 10, 12, 0);
  const copy = text(
    render({
      conversation: {
        ...conversation,
        startedAt: older.toISOString(),
        createdAt: older.toISOString(),
        finishedAt: older.toISOString(),
        status: 'completed',
      },
    }),
  );
  const chip = conversationDetailDateChipCopy(older.toISOString(), Date.now());
  const dated = clockLabel(older.getTime(), Date.now());
  expect(copy).not.toContain('Started ·');
  expect(copy).toContain(chip);
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain(dated);
});

test('conversation details omit Flutter GetSummaryWidgets unused finishedAt clock', () => {
  const copy = text(
    render({
      conversation: {
        ...conversation,
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:05:00.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('Finished ·');
});

test('conversation details omit Flutter GetSummaryWidgets unused status chip', () => {
  const copy = text(
    render({
      conversation: {
        ...conversation,
        startedAt: '2026-09-07T12:00:00.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('Status ·');
  expect(copy).not.toContain('Completed');
});

test('conversation details omit Flutter GetSummaryWidgets unused capturedAt clock', () => {
  const copy = text(
    render({
      conversation: {
        ...conversation,
        startedAt: '2026-09-07T12:00:00.000Z',
        capturedAtMs: Date.parse('2026-09-07T12:00:00.000Z'),
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('Captured (device time)');
});

test('legacy conversation details name GET started from created_at when started_at is missing', () => {
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
  const missingStart = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        startedAt: null,
        createdAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:05:00.000Z',
        status: 'completed',
      },
    }),
  );
  expect(missingStart).not.toContain('Started ·');
  expect(missingStart).not.toContain('Time unavailable');
  expect(missingStart).not.toContain('Duration ·');
});

test('legacy conversation details name GET duration from transcript span', () => {
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
              text: 'Hello',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 90,
            },
            {
              text: 'Later',
              speaker: 'SPEAKER_01',
              isUser: false,
              start: 120,
              end: 150,
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
      conversation: {
        ...conversation,
        id: 'old-1',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T13:00:00.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Duration ·');
  expect(copy).toContain('2 mins 30 secs');
  expect(copy).not.toContain('1 hr');
  expect(copy).not.toContain('Duration unavailable');
});

test('canonical recording details name GET duration from transcript span', () => {
  mockRecording.mockReturnValue({
    result: {
      status: 'loaded',
      value: {
        state: 'completed',
        text: 'Hello Later',
        discardedLeadingPackets: 0,
        segments: [
          {
            text: 'Hello',
            speaker: 'SPEAKER_00',
            isUser: false,
            start: 0,
            end: 90,
          },
          {
            text: 'Later',
            speaker: 'SPEAKER_01',
            isUser: false,
            start: 120,
            end: 150,
          },
        ],
      },
    },
    reload: jest.fn(),
  });
  const copy = text(
    render({
      conversation: {
        ...conversation,
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T13:00:00.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Duration ·');
  expect(copy).toContain('2 mins 30 secs');
  expect(copy).not.toContain('1 hr');
  expect(copy).not.toContain('Duration unavailable');
});

test('legacy conversation details name GET transcript duration 1 sec', () => {
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
              text: 'Hi',
              speaker: 'SPEAKER_00',
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
      conversation: {
        ...conversation,
        id: 'old-1',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:00:20.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Duration ·');
  expect(copy).toContain('1 sec');
  expect(copy).not.toContain('1 secs');
  expect(copy).not.toContain('< 1 min');
  expect(copy).not.toContain('20s');
});

test('canonical recording details name GET transcript duration 1 sec', () => {
  mockRecording.mockReturnValue({
    result: {
      status: 'loaded',
      value: {
        state: 'completed',
        text: 'Hi',
        discardedLeadingPackets: 0,
        segments: [
          {
            text: 'Hi',
            speaker: 'SPEAKER_00',
            isUser: false,
            start: 0,
            end: 1,
          },
        ],
      },
    },
    reload: jest.fn(),
  });
  const copy = text(
    render({
      conversation: {
        ...conversation,
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:00:20.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Duration ·');
  expect(copy).toContain('1 sec');
  expect(copy).not.toContain('1 secs');
  expect(copy).not.toContain('< 1 min');
});

test('listen details omit wall-clock Duration when GET transcript span is missing', () => {
  const copy = text(
    render({
      conversation: {
        ...conversation,
        id: 'listen:short-one',
        source: 'listen',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:00:20.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('< 1 min');
  expect(copy).not.toContain('Duration unavailable');
});

test('listen details name GET transcriptEndSeconds like Flutter GetSummaryWidgets', () => {
  const copy = text(
    render({
      conversation: {
        ...conversation,
        id: 'listen:span-one',
        source: 'listen',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T13:00:00.000Z',
        status: 'completed',
        transcriptEndSeconds: 150,
      },
    }),
  );
  expect(copy).not.toContain('Duration ·');
  expect(copy).toContain('2 mins 30 secs');
  expect(copy).not.toContain('1 hr');
  expect(copy).not.toContain('< 1 min');
  expect(copy).not.toContain('2m');
});

test('canonical recording details omit Duration when transcript span is empty', () => {
  mockRecording.mockReturnValue({
    result: {
      status: 'loaded',
      value: {
        state: 'completed',
        text: '',
        discardedLeadingPackets: 0,
        segments: [],
      },
    },
    reload: jest.fn(),
  });
  const copy = text(
    render({
      conversation: {
        ...conversation,
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T13:00:00.000Z',
        status: 'completed',
      },
    }),
  );
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('1 hr');
  expect(copy).not.toContain('Duration unavailable');
});

test('legacy in-progress chats omit Finished like canonical detail', () => {
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
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        status: 'in_progress',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: null,
      },
    }),
  );
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('Status ·');
  expect(copy).not.toContain('In progress');
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('Duration unavailable');
  expect(copy).not.toContain('in_progress');
});

test('legacy conversation details name GET action items without a write toggle', () => {
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
        actionItems: [
          {description: 'Call Alex', completed: true},
          {description: 'Send notes', completed: false},
        ],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        status: 'in_progress',
      },
    }),
  );
  expect(copy).toContain('Action Items');
  expect(copy).toContain(conversationActionItemsTodoCopy());
  expect(copy).toContain('Send notes');
  expect(copy).toContain(conversationActionItemsCompletedCopy());
  expect(copy).toContain('Call Alex');
  expect(copy).not.toContain(conversationActionItemsNoPendingCopy());
  expect(copy).not.toContain(conversationActionItemsNoCompletedCopy());
  expect(copy).not.toContain(conversationActionItemsEmptyCopy());
  expect(copy).not.toContain('in_progress');
});

test('legacy conversation details name Flutter ActionItemsTab empty GET descriptions', () => {
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
        actionItems: [{description: '\u0085', completed: false}],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  const whitespaceDescriptions = view.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return (
      children === '\u0085' ||
      (Array.isArray(children) && children.some(child => child === '\u0085'))
    );
  });
  expect(whitespaceDescriptions.length).toBeGreaterThan(0);
  expect(copy).toContain(conversationActionItemsTodoCopy());
  expect(copy).toContain(conversationActionItemsCompletedCopy());
  expect(copy).toContain(conversationActionItemsNoCompletedCopy());
  expect(copy).not.toContain(conversationActionItemsEmptyCopy());
  expect(copy).not.toContain(conversationActionItemsEmptyDescriptionCopy());
  expect(copy).not.toContain(conversationActionItemsNoPendingCopy());
  expect(copy).toContain('\u0085');
  expect(copy).not.toContain('Create Action Item');
});

test('legacy conversation details name Flutter ActionItemsTab empty GET chrome', () => {
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
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain(conversationActionItemsEmptyCopy());
  expect(copy).toContain(conversationActionItemsEmptyDescriptionCopy());
  expect(copy).not.toContain(conversationActionItemsTodoCopy());
  expect(copy).not.toContain(conversationActionItemsCompletedCopy());
  expect(copy).not.toContain(conversationActionItemsNoPendingCopy());
  expect(copy).not.toContain(conversationActionItemsNoCompletedCopy());
  expect(copy).not.toContain('Create Action Item');
});

test('legacy conversation details name GET action-item To-Do empty groups without a write toggle', () => {
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
        actionItems: [{description: 'Send notes', completed: false}],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const pending = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(pending).toContain(conversationActionItemsTodoCopy());
  expect(pending).toContain('Send notes');
  expect(pending).toContain(conversationActionItemsCompletedCopy());
  expect(pending).toContain(conversationActionItemsNoCompletedCopy());
  expect(pending).not.toContain(conversationActionItemsNoPendingCopy());
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
        actionItems: [{description: 'Call Alex', completed: true}],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const done = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(done).toContain(conversationActionItemsTodoCopy());
  expect(done).toContain(conversationActionItemsNoPendingCopy());
  expect(done).toContain(conversationActionItemsCompletedCopy());
  expect(done).toContain('Call Alex');
  expect(done).not.toContain(conversationActionItemsNoCompletedCopy());
});

test('legacy conversation details name GET geolocation address', () => {
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
        actionItems: [],
        locationAddress: '123 Market St, San Francisco',
        locationMapsUrl:
          'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain('123 Market St, San Francisco');
  const discarded = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', discarded: true},
    }),
  );
  expect(discarded).not.toContain('123 Market St, San Francisco');
});

test('legacy conversation details name Flutter GetGeolocationWidgets short address', () => {
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
        actionItems: [],
        locationAddress: 'Mission District, San Francisco',
        locationMapsUrl:
          'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain('Mission District, San Francisco');
  expect(copy).not.toContain('123 Market St');
  expect(copy).not.toContain('CA 94103');
});

test('legacy conversation details name GET geolocation maps open', () => {
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
        actionItems: [],
        locationAddress: '123 Market St, San Francisco',
        locationMapsUrl:
          'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(view)).toContain('123 Market St, San Francisco');
  const links = view.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Open in Maps' &&
      typeof node.props.onPress === 'function',
  );
  expect(links.length).toBeGreaterThan(0);
  const openURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  act(() => {
    links[0].props.onPress();
  });
  expect(openURL).toHaveBeenCalledWith(
    'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
  );
  openURL.mockRestore();
});

test('legacy conversation details name Flutter GetGeolocationWidgets whitespace GET address without Unknown location', () => {
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
        actionItems: [],
        locationAddress: '',
        locationMapsUrl:
          'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  expect(copy).not.toContain(conversationUnknownLocationCopy());
  const links = view.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Open in Maps' &&
      typeof node.props.onPress === 'function',
  );
  expect(links.length).toBeGreaterThan(0);
  const emptyAddresses = view.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return (
      children === '' ||
      (Array.isArray(children) && children.some(child => child === ''))
    );
  });
  expect(emptyAddresses.length).toBeGreaterThan(0);
});

test('legacy conversation details name Flutter GetGeolocationWidgets empty GET address whitespace', () => {
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
        actionItems: [],
        locationAddress: ' \t',
        locationMapsUrl:
          'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const whitespace = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    whitespace.root.findAll(
      node => node.type === Text && node.props.children === ' \t',
    ).length,
  ).toBeGreaterThan(0);
  expect(text(whitespace)).toContain(' \t');
  expect(text(whitespace)).not.toContain(conversationUnknownLocationCopy());
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
        actionItems: [],
        locationAddress: '  Mission  ',
        locationMapsUrl:
          'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const padded = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    padded.root.findAll(
      node => node.type === Text && node.props.children === '  Mission  ',
    ).length,
  ).toBeGreaterThan(0);
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
        actionItems: [],
        locationAddress: '\u0085',
        locationMapsUrl:
          'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const nextLine = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    nextLine.root.findAll(
      node => node.type === Text && node.props.children === '\u0085',
    ).length,
  ).toBeGreaterThan(0);
  expect(text(nextLine)).not.toContain(conversationUnknownLocationCopy());
});

test('legacy conversation details name Flutter AppResultDetailWidget empty GET names without Unknown App', () => {
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
        actionItems: [],
        appSummary: 'App wrote this recap',
        appSummaryName: ' \t\n',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(view)).toContain(' \t\n');
  expect(text(view)).toContain('App wrote this recap');
  expect(text(view)).not.toContain(conversationUnknownAppCopy());
  expect(text(view)).not.toContain('App name unavailable');
});

test('legacy conversation details name Flutter AppResultDetailWidget empty GET descriptions', () => {
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
        actionItems: [],
        appSummary: 'App wrote this recap',
        appSummaryName: 'Notes',
        appSummaryDescription: ' \t\n',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(view)).toContain(' \t\n');
  expect(text(view)).toContain('Notes');
  expect(text(view)).toContain('App wrote this recap');
  expect(text(view)).not.toContain('App details unavailable');
  expect(text(view)).not.toContain('App description unavailable');
});

test('legacy conversation details name GET app result content', () => {
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
        actionItems: [],
        appSummary: 'App wrote this recap',
        appSummaryName: 'Notes',
        appSummaryDescription: 'Saves notes from calls',
        appSummaryImageUri: 'https://cdn.example.test/notes.png',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  const imageUri = 'https://cdn.example.test/notes.png';
  expect(copy).toContain('App wrote this recap');
  expect(copy).toContain('Notes');
  expect(copy).toContain('Saves notes from calls');
  expect(copy).not.toContain(conversationUnknownAppCopy());
  expect(copy).not.toContain('Official');
  expect(copy).not.toContain('raw.githubusercontent.com');
  expect(
    view.root.findAll(node => node.props.source?.uri === imageUri).length,
  ).toBeGreaterThan(0);
  expect(
    view.root.findAll(node => node.props.source?.uri === imageUri)[0]?.props
      .accessibilityLabel,
  ).toBe('Notes');
  expect(
    view.root.findAll(node => node.props.source?.uri === imageUri)[0]?.props
      .onPress,
  ).toBeUndefined();
  const discardedView = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1', discarded: true},
  });
  const discarded = text(discardedView);
  expect(discarded).not.toContain('App wrote this recap');
  expect(discarded).not.toContain('Notes');
  expect(discarded).not.toContain('Saves notes from calls');
  expect(
    discardedView.root.findAll(node => node.props.source?.uri === imageUri),
  ).toHaveLength(0);
});

test('legacy conversation details name Flutter AppResultDetailWidget padded GET image instead of remapping to a CDN chip', () => {
  const exactUri = 'https://cdn.example.test/notes.png';
  const trailingUri = 'https://cdn.example.test/notes.png ';
  const paddedUri = '  https://cdn.example.test/notes.png  ';
  const httpsUri = 'HTTPS://cdn.example.test/notes.png';
  const detail = {
    id: 'old-1',
    title: 'A real conversation',
    summary: 'Summary',
    locked: false,
    sections: [],
    actionItems: [],
    appSummary: 'App wrote this recap',
    appSummaryName: 'Notes',
    appSummaryDescription: 'Saves notes from calls',
    transcript: {status: 'loaded', segments: []},
  };
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {...detail, appSummaryImageUri: trailingUri},
    },
    reload: jest.fn(),
  });
  const trailing = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    trailing.root.findAll(node => node.props.source?.uri === trailingUri)
      .length,
  ).toBeGreaterThan(0);
  expect(
    trailing.root.findAll(node => node.props.source?.uri === exactUri),
  ).toHaveLength(0);
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {...detail, appSummaryImageUri: paddedUri},
    },
    reload: jest.fn(),
  });
  const padded = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    padded.root.findAll(
      node =>
        typeof node.props.source?.uri === 'string' &&
        node.props.source.uri.includes('cdn.example.test/notes.png'),
    ),
  ).toHaveLength(0);
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {...detail, appSummaryImageUri: httpsUri},
    },
    reload: jest.fn(),
  });
  const https = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    https.root.findAll(
      node =>
        typeof node.props.source?.uri === 'string' &&
        node.props.source.uri
          .toLowerCase()
          .includes('cdn.example.test/notes.png'),
    ),
  ).toHaveLength(0);
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {...detail, appSummaryImageUri: exactUri},
    },
    reload: jest.fn(),
  });
  const exact = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    exact.root.findAll(node => node.props.source?.uri === exactUri).length,
  ).toBeGreaterThan(0);
});

test('legacy conversation details name Flutter Unknown App when the catalog misses', () => {
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
        actionItems: [],
        appSummary: 'App wrote this recap',
        appSummaryName: conversationUnknownAppCopy(),
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  expect(copy).toContain('App wrote this recap');
  expect(copy).toContain(conversationUnknownAppCopy());
  expect(copy).not.toContain('Official');
  expect(
    view.root.findAll(node => node.props.source?.uri !== undefined),
  ).toHaveLength(0);
  const discarded = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', discarded: true},
    }),
  );
  expect(discarded).not.toContain('App wrote this recap');
  expect(discarded).not.toContain(conversationUnknownAppCopy());
});

test('legacy conversation details name a failed GET app catalog instead of empty success', () => {
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
        actionItems: [],
        appSummary: 'App wrote this recap',
        appsError: desktopBackendServiceCopy,
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain('App wrote this recap');
  expect(copy).toContain(desktopBackendServiceCopy);
  expect(copy).not.toContain(conversationUnknownAppCopy());
  expect(copy).not.toContain('Official');
  const discarded = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', discarded: true},
    }),
  );
  expect(discarded).not.toContain('App wrote this recap');
  expect(discarded).not.toContain(desktopBackendServiceCopy);
});

test('legacy conversation details name Flutter first-party Summary when appId is null', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Day recap notes',
        locked: false,
        sections: [],
        actionItems: [],
        appSummary: 'App wrote this recap',
        appSummaryName: conversationFirstPartySummaryCopy(),
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  expect(copy).toContain('Day recap notes');
  expect(copy).toContain('App wrote this recap');
  expect(copy).toContain(conversationFirstPartySummaryCopy());
  expect(copy).not.toContain(conversationUnknownAppCopy());
  expect(copy).not.toContain('Official');
  expect(
    view.root.findAll(node => node.props.source?.uri !== undefined),
  ).toHaveLength(0);
  const discarded = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', discarded: true},
    }),
  );
  expect(discarded).not.toContain('Day recap notes');
  expect(discarded).not.toContain('App wrote this recap');
  expect(discarded).not.toContain(conversationFirstPartySummaryCopy());
});

test('legacy details name Flutter noSummaryForConversation when GET has no summarized app', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: '',
        locked: false,
        sections: [],
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain(conversationNoSummaryCopy());
  expect(copy).not.toContain(conversationNoSummaryForAppCopy());
  expect(copy).not.toContain('Conversation summary unavailable');
  expect(copy).not.toContain('Conversation summary is not ready yet.');
  expect(copy).not.toContain('Generate Summary');
  const processing = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', status: 'processing'},
    }),
  );
  expect(processing).toContain(processingConversationNoSummaryCopy());
  expect(processing).not.toContain(conversationNoSummaryCopy());
  expect(processing).not.toContain(conversationNoSummaryForAppCopy());
  expect(processing).not.toContain('Conversation summary is not ready yet.');
  expect(processing).not.toContain('Generate Summary');
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: '',
        locked: false,
        sections: [],
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Recorded words',
              speaker: 'SPEAKER_00',
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
  const processingWithTranscript = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', status: 'processing'},
    }),
  );
  expect(processingWithTranscript).toContain('Recorded words');
  expect(processingWithTranscript).not.toContain(conversationNoSummaryCopy());
  expect(processingWithTranscript).not.toContain(
    processingConversationNoSummaryCopy(),
  );
  expect(processingWithTranscript).not.toContain('Generate Summary');
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: '',
        locked: false,
        sections: [{heading: 'Notes', bodyMarkdown: 'Full notes'}],
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const withSections = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(withSections).toContain('Notes');
  expect(withSections).toContain('Full notes');
  expect(withSections).not.toContain(conversationNoSummaryCopy());
  expect(withSections).not.toContain(conversationNoSummaryForAppCopy());
  expect(withSections).not.toContain('Conversation summary unavailable');
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: '',
        locked: false,
        sections: [],
        actionItems: [],
        appSummary: 'App wrote this recap',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const withApp = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(withApp).toContain('App wrote this recap');
  expect(withApp).not.toContain(conversationNoSummaryCopy());
  expect(withApp).not.toContain(conversationNoSummaryForAppCopy());
  expect(withApp).not.toContain('Conversation summary unavailable');
});

test('legacy details name Flutter AppResultDetailWidget whitespace GET overview as noSummaryForApp', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: ' \t\n',
        locked: false,
        sections: [],
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain(conversationNoSummaryForAppCopy());
  expect(copy).not.toContain(conversationNoSummaryCopy());
  expect(copy).not.toContain(conversationFirstPartySummaryCopy());
  expect(copy).not.toContain('Conversation summary unavailable');
  expect(copy).not.toContain('Generate Summary');
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: '',
        locked: false,
        sections: [{heading: ' \t\n', bodyMarkdown: ' \t'}],
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const whitespaceSections = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(whitespaceSections).toContain(conversationNoSummaryForAppCopy());
  expect(whitespaceSections).not.toContain(conversationNoSummaryCopy());
  const processing = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', status: 'processing'},
    }),
  );
  expect(processing).toContain(processingConversationNoSummaryCopy());
  expect(processing).not.toContain(conversationNoSummaryForAppCopy());
  expect(processing).not.toContain(conversationNoSummaryCopy());
  expect(processing).not.toContain('Generate Summary');
});

test('legacy processing details name Flutter inProgress instead of GET title', () => {
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
  const processing = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', status: 'processing'},
    }),
  );
  expect(processing).toContain(processingConversationDetailTitleCopy());
  expect(processing).not.toContain('A real conversation');
  expect(processing).not.toContain('Processing conversation…');
  const merging = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        title: '',
        status: 'merging',
      },
    }),
  );
  expect(merging).toContain(processingConversationDetailTitleCopy());
  expect(merging).not.toContain('Conversation title unavailable');
  expect(merging).not.toContain('Processing conversation…');
  const completed = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(completed).toContain('A real conversation');
  expect(completed).not.toContain(processingConversationDetailTitleCopy());
});

test('legacy conversation details name Flutter GetEditTextField empty GET title whitespace', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: ' \t\n',
        summary: 'Summary',
        locked: false,
        sections: [],
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const whitespace = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1', title: ' \t\n'},
  });
  expect(
    whitespace.root.findAll(
      node => node.type === Text && node.props.children === ' \t\n',
    ).length,
  ).toBeGreaterThan(0);
  expect(text(whitespace)).toContain(' \t\n');
  expect(text(whitespace)).not.toContain(
    processingConversationDetailTitleCopy(),
  );
  expect(text(whitespace)).not.toContain('Conversation title unavailable');
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: '  Morning walk  ',
        summary: 'Summary',
        locked: false,
        sections: [],
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const padded = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1', title: '  Morning walk  '},
  });
  expect(
    padded.root.findAll(
      node => node.type === Text && node.props.children === '  Morning walk  ',
    ).length,
  ).toBeGreaterThan(0);
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: '\u0085',
        summary: 'Summary',
        locked: false,
        sections: [],
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const nextLine = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1', title: '\u0085'},
  });
  expect(
    nextLine.root.findAll(
      node => node.type === Text && node.props.children === '\u0085',
    ).length,
  ).toBeGreaterThan(0);
});

test('legacy processing details name Flutter Content tab instead of Transcript', () => {
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
  const processing = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', status: 'processing'},
    }),
  );
  expect(processing).toContain(
    processingConversationDetailContentTabCopy('omi'),
  );
  expect(processing).not.toContain('Transcript');
  expect(processing).not.toContain('🎙️');
  expect(processing).not.toContain('📸');
  const photos = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        status: 'processing',
        source: 'openglass',
      },
    }),
  );
  expect(photos).toContain(
    processingConversationDetailContentTabCopy('openglass'),
  );
  expect(photos).not.toContain('Transcript');
  const rawData = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        status: 'processing',
        source: 'screenpipe',
      },
    }),
  );
  expect(rawData).toContain(
    processingConversationDetailContentTabCopy('screenpipe'),
  );
  expect(rawData).not.toContain('Transcript');
  const paddedScreenpipe = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        status: 'processing',
        source: '  screenpipe  ',
      },
    }),
  );
  expect(paddedScreenpipe).toContain(
    processingConversationDetailContentTabCopy('  screenpipe  '),
  );
  expect(paddedScreenpipe).not.toContain('Raw Data');
  expect(paddedScreenpipe).not.toContain('Transcript');
  const paddedOpenglass = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        status: 'processing',
        source: '  openglass  ',
      },
    }),
  );
  expect(paddedOpenglass).toContain(
    processingConversationDetailContentTabCopy('  openglass  '),
  );
  expect(paddedOpenglass).not.toContain('Photos');
  expect(paddedOpenglass).not.toContain('Transcript');
  const merging = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', status: 'merging'},
    }),
  );
  expect(merging).toContain(
    processingConversationDetailContentTabCopy('omi'),
  );
  expect(merging).not.toContain('Transcript');
  const completed = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(completed).toContain('Transcript');
  expect(completed).not.toContain(
    processingConversationDetailContentTabCopy('omi'),
  );
});

test('legacy discarded details name Discarded Conversation instead of structured title', () => {
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        id: 'old-1',
        title: 'A real conversation',
        summary: 'Summary that Flutter hides',
        locked: false,
        sections: [{heading: 'Hidden notes', bodyMarkdown: 'Full notes'}],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1', discarded: true},
  });
  const copy = text(view);
  expect(copy).toContain('Discarded Conversation');
  expect(
    view.root.findAll(node => node.props.children === 'Discarded'),
  ).toHaveLength(0);
  expect(copy).not.toContain('A real conversation');
  expect(copy).not.toContain('Summary that Flutter hides');
  expect(copy).not.toContain('Hidden notes');
  expect(copy).not.toContain('Full notes');
  expect(copy).not.toContain('want to retry');
});

test('canonical discarded details name Discarded Conversation instead of structured title', () => {
  const view = render({
    conversation: {
      ...conversation,
      discarded: true,
      title: 'Planning',
      summary: 'Summary that Flutter hides',
    },
  });
  const copy = text(view);
  expect(copy).toContain('Discarded Conversation');
  expect(
    view.root.findAll(node => node.props.children === 'Discarded'),
  ).toHaveLength(0);
  expect(copy).not.toContain('Planning');
  expect(copy).not.toContain('Summary that Flutter hides');
  expect(copy).not.toContain('want to retry');
});

test('conversation details omit Flutter GetSummaryWidgets unused Discarded chip', () => {
  const view = render({
    conversation: {...conversation, discarded: true},
  });
  expect(text(view)).toContain('Discarded Conversation');
  expect(
    view.root.findAll(node => node.props.children === 'Discarded'),
  ).toHaveLength(0);
});

test('conversation details omit Flutter GetSummaryWidgets unused Locked chip', () => {
  const view = render({
    conversation: {...conversation, locked: true},
  });
  expect(text(view)).not.toContain('Locked');
  expect(
    view.root.findAll(node => node.props.children === 'Locked'),
  ).toHaveLength(0);
});

test('conversation details omit Flutter GetSummaryWidgets unused Started and Duration prefixes', () => {
  const view = render({
    conversation: {
      ...conversation,
      startedAt: '2026-09-07T12:00:00.000Z',
      transcriptEndSeconds: 20,
    },
  });
  const copy = text(view);
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).toContain(
    conversationDetailDateChipCopy('2026-09-07T12:00:00.000Z'),
  );
});

test('conversation details name Flutter GetSummaryWidgets No Folder chip', () => {
  const recording = render({
    conversation: {...conversation, folderId: null},
  });
  expect(text(recording)).toContain(conversationNoFolderCopy());
  const chat = render({
    conversation: {
      ...conversation,
      id: 'chat:named-session',
      source: 'chat',
      folderId: null,
    },
  });
  expect(text(chat)).toContain(conversationNoFolderCopy());
  const listen = render({
    conversation: {
      ...conversation,
      id: 'c1',
      source: 'omi',
      folderId: null,
    },
  });
  expect(text(listen)).toContain(conversationNoFolderCopy());
});

test('conversation details name GET private and shared visibility', () => {
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
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const shared = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', visibility: 'shared'},
    }),
  );
  expect(shared).toContain('Shared');
  const published = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', visibility: 'public'},
    }),
  );
  expect(published).toContain('Shared');
  expect(published).not.toContain('Public');
  const hidden = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', visibility: 'private'},
    }),
  );
  expect(hidden).toContain('Private');
  expect(hidden).not.toContain('Shared');
  expect(hidden).not.toContain('Public');
});

test('legacy conversation details name Flutter CalendarEventDetailsSheet empty GET titles', () => {
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
        actionItems: [],
        calendarEvent: {
          title: ' \t\n',
          attendees: [],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const whitespaceTitles = view.root.findAll(
    node => node.type === Text && node.props.children === ' \t\n',
  );
  expect(whitespaceTitles.length).toBeGreaterThan(0);
  expect(text(view)).toContain(' \t\n');
  expect(text(view)).toContain('3:00 PM – 4:00 PM');
  expect(text(view)).not.toContain('Calendar event unavailable');
  expect(text(view)).not.toContain('Event title unavailable');
});

test('legacy conversation details name Flutter GetSummaryWidgets empty GET attendees', () => {
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: [' \t\n'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const emptyAttendees = view.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return (
      children === '' ||
      (Array.isArray(children) && children.some(child => child === ''))
    );
  });
  expect(emptyAttendees.length).toBeGreaterThan(0);
  expect(text(view)).toContain('Standup');
  expect(text(view)).toContain(' \t\n');
  expect(text(view)).toContain('3:00 PM – 4:00 PM');
  expect(text(view)).not.toContain('Attendees unavailable');
});

test('legacy conversation details name GET calendar event title and attendees', () => {
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: ['Alex Chen', 'sam@example.com'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
        },
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain('Standup');
  expect(copy).toContain('Alex Chen, sam@example.com');
  expect(copy).toContain('3:00 PM – 4:00 PM');
});

test('legacy conversation details name Flutter GetSummaryWidgets attendee chip', () => {
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: ['Alex Chen', 'sam@example.com', 'Priya Shah'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
        },
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain('Alex, Sam +1');
  expect(copy).toContain('Alex Chen, sam@example.com, Priya Shah');
  const recording = render({
    conversation: {...conversation, folderId: null},
  });
  expect(text(recording)).not.toContain('Alex, Sam +1');
});

test('legacy conversation details name Flutter GetSummaryWidgets padded GET attendee', () => {
  const detail = {
    id: 'old-1',
    title: 'A real conversation',
    summary: 'Summary',
    locked: false,
    sections: [],
    actionItems: [],
    transcript: {status: 'loaded', segments: []},
  };
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        ...detail,
        calendarEvent: {
          title: 'Standup',
          attendees: ['  Alex Chen  '],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
        },
      },
    },
    reload: jest.fn(),
  });
  const padded = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    padded.root.findAll(
      node => node.type === Text && node.props.children === 'Alex',
    ),
  ).toHaveLength(0);
  expect(
    padded.root.findAll(
      node => node.type === Text && node.props.children === '',
    ).length,
  ).toBeGreaterThan(0);
  expect(text(padded)).toContain('  Alex Chen  ');
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        ...detail,
        calendarEvent: {
          title: 'Standup',
          attendees: ['\u0085Alex Chen'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
        },
      },
    },
    reload: jest.fn(),
  });
  const nextLine = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    nextLine.root.findAll(
      node => node.type === Text && node.props.children === 'Alex',
    ),
  ).toHaveLength(0);
  expect(
    nextLine.root.findAll(
      node => node.type === Text && node.props.children === '\u0085Alex',
    ).length,
  ).toBeGreaterThan(0);
  expect(text(nextLine)).toContain('\u0085Alex Chen');
  mockLegacy.mockReturnValue({
    result: {
      status: 'loaded',
      conversationId: 'old-1',
      value: {
        ...detail,
        calendarEvent: {
          title: 'Standup',
          attendees: ['  sam@example.com'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
        },
      },
    },
    reload: jest.fn(),
  });
  const paddedEmail = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    paddedEmail.root.findAll(
      node => node.type === Text && node.props.children === 'Sam',
    ),
  ).toHaveLength(0);
  expect(
    paddedEmail.root.findAll(
      node => node.type === Text && node.props.children === '  sam',
    ).length,
  ).toBeGreaterThan(0);
  expect(text(paddedEmail)).toContain('  sam@example.com');
});

test('legacy conversation details name Flutter CalendarEventDetailsSheet empty GET html_link whitespace', () => {
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: [],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
          htmlLink: ' \t',
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const whitespaceView = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(whitespaceView)).toContain('Open in Google Calendar');
  const whitespaceLinks = whitespaceView.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Open in Google Calendar' &&
      typeof node.props.onPress === 'function',
  );
  expect(whitespaceLinks.length).toBeGreaterThan(0);
  const whitespaceOpenURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  act(() => {
    whitespaceLinks[0].props.onPress();
  });
  expect(whitespaceOpenURL).not.toHaveBeenCalled();
  whitespaceOpenURL.mockRestore();
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: [],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
          htmlLink: '\u0085',
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const nextLineView = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(nextLineView)).toContain('Open in Google Calendar');
  const nextLineLinks = nextLineView.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Open in Google Calendar' &&
      typeof node.props.onPress === 'function',
  );
  expect(nextLineLinks.length).toBeGreaterThan(0);
  const nextLineOpenURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  act(() => {
    nextLineLinks[0].props.onPress();
  });
  expect(nextLineOpenURL).not.toHaveBeenCalled();
  nextLineOpenURL.mockRestore();
});

test('legacy conversation details name Flutter CalendarEventDetailsSheet empty GET html_link', () => {
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: [],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
          htmlLink: '',
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(view)).toContain('Open in Google Calendar');
  const links = view.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Open in Google Calendar' &&
      typeof node.props.onPress === 'function',
  );
  expect(links.length).toBeGreaterThan(0);
  const openURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  act(() => {
    links[0].props.onPress();
  });
  expect(openURL).not.toHaveBeenCalled();
  openURL.mockRestore();
});

test('legacy conversation details name GET calendar html_link', () => {
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: ['Alex Chen'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
          htmlLink: 'https://calendar.google.com/calendar/event?eid=standup',
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(view)).toContain('Standup');
  expect(text(view)).toContain('Open in Google Calendar');
  const links = view.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Open in Google Calendar' &&
      typeof node.props.onPress === 'function',
  );
  expect(links.length).toBeGreaterThan(0);
  const openURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  act(() => {
    links[0].props.onPress();
  });
  expect(openURL).toHaveBeenCalledWith(
    'https://calendar.google.com/calendar/event?eid=standup',
  );
  openURL.mockRestore();
});

test('legacy conversation details name GET calendar Share with attendees', () => {
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: ['Alex Chen'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
          shareMailto: `mailto:alex@example.com,sam@example.com?subject=${encodeURIComponent(
            'Notes: Standup',
          )}`,
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(view)).toContain('Share with attendees');
  const links = view.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Share with attendees' &&
      typeof node.props.onPress === 'function',
  );
  expect(links.length).toBeGreaterThan(0);
  const openURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  act(() => {
    links[0].props.onPress();
  });
  expect(openURL).toHaveBeenCalledWith(
    `mailto:alex@example.com,sam@example.com?subject=${encodeURIComponent(
      'Notes: Standup',
    )}`,
  );
  openURL.mockRestore();
});

test('legacy conversation details name Flutter CalendarEventDetailsSheet padded GET attendee_emails', () => {
  const paddedMailto = `mailto:  sam@example.com  ?subject=${encodeURIComponent(
    'Notes: Standup',
  )}`;
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: ['Alex Chen'],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
          shareMailto: paddedMailto,
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const padded = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(padded)).toContain('Share with attendees');
  const paddedLinks = padded.root.findAll(
    node =>
      node.props.accessibilityRole === 'link' &&
      node.props.accessibilityLabel === 'Share with attendees' &&
      typeof node.props.onPress === 'function',
  );
  expect(paddedLinks.length).toBeGreaterThan(0);
  const paddedOpenURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  act(() => {
    paddedLinks[0].props.onPress();
  });
  expect(paddedOpenURL).toHaveBeenCalledWith(paddedMailto);
  paddedOpenURL.mockRestore();
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
        actionItems: [],
        calendarEvent: {
          title: 'Standup',
          attendees: [],
          startCopy: '3:00 PM',
          endCopy: '4:00 PM',
          shareMailto: `mailto: \t,?subject=${encodeURIComponent(
            'Notes: Standup',
          )}`,
        },
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const whitespace = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(whitespace)).toContain('Share with attendees');
});

test('legacy conversation details omit Flutter PhotosGrid photo-count text', () => {
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
        actionItems: [],
        photoCount: 3,
        photoCaptions: ['Whiteboard notes'],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).not.toContain('3 photos');
  expect(copy).toContain('Whiteboard notes');
});

test('legacy conversation details name GET discarded photos and analyzing captions', () => {
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
        actionItems: [],
        photoCount: 3,
        photoCaptions: [
          'Whiteboard notes',
          'This photo was discarded as it was not significant.',
          'Analyzing...',
        ],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).not.toContain('3 photos');
  expect(copy).toContain('Whiteboard notes');
  expect(copy).toContain(
    'This photo was discarded as it was not significant.',
  );
  expect(copy).toContain('Analyzing...');
});

test('legacy conversation details paint GET photo base64 without a viewer', () => {
  const uri =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
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
        actionItems: [],
        photoCount: 2,
        photoCaptions: ['Whiteboard notes'],
        photoRows: [
          {caption: 'Whiteboard notes', imageUri: uri},
          {caption: 'Stored elsewhere'},
        ],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  expect(copy).not.toContain('2 photos');
  expect(copy).toContain('Whiteboard notes');
  expect(copy).toContain('Stored elsewhere');
  expect(
    view.root.findAll(node => node.props.source?.uri === uri).length,
  ).toBeGreaterThan(0);
  expect(
    view.root.findAll(
      node =>
        typeof node.props.source?.uri === 'string' &&
        node.props.source.uri.startsWith('data:image/') &&
        node.props.source.uri !== uri,
    ),
  ).toHaveLength(0);
  expect(
    view.root.findAll(node => node.props.source?.uri === uri)[0]?.props
      .onPress,
  ).toBeUndefined();
});

test('legacy conversation details name GET invalid inline photo File unavailable', () => {
  const uri =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
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
        actionItems: [],
        photoCount: 3,
        photoCaptions: ['Whiteboard notes', 'Corrupt', 'Stored elsewhere'],
        photoRows: [
          {caption: 'Whiteboard notes', imageUri: uri},
          {caption: 'Corrupt', unavailableCopy: conversationPhotoUnavailableCopy()},
          {caption: 'Stored elsewhere'},
        ],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  expect(copy).not.toContain('3 photos');
  expect(copy).toContain('Whiteboard notes');
  expect(copy).toContain(conversationPhotoUnavailableCopy());
  expect(copy).toContain('Corrupt');
  expect(copy).toContain('Stored elsewhere');
  expect(
    view.root.findAll(node => node.props.source?.uri === uri).length,
  ).toBeGreaterThan(0);
});

test('legacy conversation details name GET empty inline photo File unavailable', () => {
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
        actionItems: [],
        photoCount: 2,
        photoCaptions: ['No bytes', 'Stored empty'],
        photoRows: [
          {caption: 'No bytes', unavailableCopy: conversationPhotoUnavailableCopy()},
          {caption: 'Stored empty'},
        ],
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).not.toContain('2 photos');
  expect(copy).toContain('No bytes');
  expect(copy).toContain(conversationPhotoUnavailableCopy());
  expect(copy).toContain('Stored empty');
});

test('legacy conversation details name Flutter MediaViewerPage whitespace GET photo descriptions', () => {
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
        actionItems: [],
        photoCount: 2,
        photoCaptions: ['Whiteboard notes', ' \t'],
        photoRows: [{caption: 'Whiteboard notes'}, {caption: ' \t'}],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  expect(copy).toContain('Whiteboard notes');
  expect(copy).toContain(' \t');
  expect(copy).not.toContain('2 photos');
  expect(
    view.root.findAll(
      node => node.type === Text && node.props.children === ' \t',
    ).length,
  ).toBeGreaterThan(0);
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
        actionItems: [],
        photoCount: 2,
        photoCaptions: ['  Whiteboard notes  ', '\u0085'],
        photoRows: [
          {caption: '  Whiteboard notes  '},
          {caption: '\u0085'},
        ],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const padded = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(
    padded.root.findAll(
      node =>
        node.type === Text && node.props.children === '  Whiteboard notes  ',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    padded.root.findAll(
      node => node.type === Text && node.props.children === '\u0085',
    ).length,
  ).toBeGreaterThan(0);
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
        actionItems: [],
        photoCount: 1,
        photoCaptions: [],
        photoRows: [{caption: ''}],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const empty = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(empty)).not.toContain('1 photos');
  expect(text(empty)).not.toContain('Caption unavailable');
});

test('legacy conversation details name GET folder name and Flutter No Folder otherwise', () => {
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
        actionItems: [],
        folderName: 'Work',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        folderId: 'folder-work',
      },
    }),
  );
  expect(copy).toContain('Work');
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
        actionItems: [],
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const omitted = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        folderId: 'folder-work',
      },
    }),
  );
  expect(omitted).toContain(conversationNoFolderCopy());
  expect(omitted).not.toContain('folder-work');
});

test('legacy conversation details name Flutter GetSummaryWidgets empty GET folder name without No Folder', () => {
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
        actionItems: [],
        folderName: ' \t\n',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {
      ...conversation,
      id: 'old-1',
      folderId: 'folder-empty',
    },
  });
  const whitespaceFolders = view.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return (
      children === ' \t\n' ||
      (Array.isArray(children) && children.some(child => child === ' \t\n'))
    );
  });
  expect(whitespaceFolders.length).toBeGreaterThan(0);
  expect(text(view)).toContain(' \t\n');
  expect(text(view)).not.toContain(conversationNoFolderCopy());
  expect(text(view)).not.toContain('folder-empty');
});

test('legacy conversation details name GET folder color without hex copy', () => {
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
        actionItems: [],
        folderName: 'Work',
        folderColor: '#3B82F6',
        folderIcon: '💼',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {
      ...conversation,
      id: 'old-1',
      folderId: 'folder-work',
    },
  });
  expect(text(view)).toContain('Work');
  expect(text(view)).toContain('💼');
  expect(text(view)).not.toContain('#3B82F6');
  const folder = view.root.find(
    node =>
      node.type === Text &&
      (Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children]
      ).includes('Work'),
  );
  const style = Object.assign(
    {},
    ...[folder.props.style]
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(style.color).toBe('#3B82F6');
});

test('legacy conversation details name GET external_data text when the transcript is empty', () => {
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
        actionItems: [],
        externalText: 'Imported Slack thread',
        transcript: {status: 'loaded', segments: []},
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
  expect(copy).toContain('Imported Slack thread');
  expect(copy).not.toContain('The transcript is empty.');
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
        actionItems: [],
        externalText: ' \t\n',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const whitespace = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  expect(text(whitespace)).toContain(' \t\n');
  expect(text(whitespace)).not.toContain('The transcript is empty.');
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
        actionItems: [],
        externalText: '',
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const empty = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const emptyExternal = empty.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return children === '';
  });
  expect(emptyExternal.length).toBeGreaterThan(0);
  expect(text(empty)).not.toContain('The transcript is empty.');
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
        actionItems: [],
        externalText: 'Imported Slack thread',
        photoCount: 2,
        transcript: {status: 'loaded', segments: []},
      },
    },
    reload: jest.fn(),
  });
  const withPhotos = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(withPhotos).not.toContain('Imported Slack thread');
});

test('legacy conversation details name GET people names on transcript speakers', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Hello there',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1,
              personName: 'Alex Chen',
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
  expect(copy).toContain('Alex Chen  ·  Hello there');
  expect(copy).not.toContain('Speaker 1');
  expect(copy).not.toContain('person-alex');
});

test('legacy conversation details name Flutter TranscriptWidget empty GET people names', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Hello there',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1,
              personName: '',
            },
            {
              text: 'Whitespace name',
              speaker: 'SPEAKER_01',
              isUser: false,
              start: 1,
              end: 2,
              personName: ' \t',
            },
            {
              text: 'Next line name',
              speaker: 'SPEAKER_02',
              isUser: false,
              start: 2,
              end: 3,
              personName: '\u0085',
            },
          ],
        },
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  const emptyNames = view.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return (
      children === '' ||
      (Array.isArray(children) && children.some(child => child === ''))
    );
  });
  expect(emptyNames.length).toBeGreaterThan(0);
  expect(copy).toContain('Hello there');
  expect(copy).toContain('Whitespace name');
  expect(copy).toContain('Next line name');
  expect(copy).toContain(' \t');
  expect(copy).toContain('\u0085');
  expect(copy).not.toContain('Speaker 1');
  expect(copy).not.toContain('Speaker 2');
  expect(copy).not.toContain('Speaker 3');
  expect(copy).not.toContain('person-empty');
});

test('legacy conversation details name GET speakers from the minimum speaker id', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'First words',
              speaker: 'SPEAKER_05',
              isUser: false,
              start: 0,
              end: 1,
            },
            {
              text: 'Later words',
              speaker: 'SPEAKER_06',
              isUser: false,
              start: 2,
              end: 3,
            },
            {
              text: 'Your turn',
              speaker: 'SPEAKER_00',
              isUser: true,
              start: 4,
              end: 5,
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
  expect(copy).toContain('Speaker 1  ·  First words');
  expect(copy).toContain('Speaker 2  ·  Later words');
  expect(copy).toContain('You  ·  Your turn');
  expect(copy).not.toContain('Speaker 6');
  expect(copy).not.toContain('Speaker 7');
});

test('legacy conversation details name GET omi speaker 99 without Speaker N', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Omi said this',
              speaker: 'SPEAKER_99',
              isUser: false,
              start: 0,
              end: 1,
              personName: 'Alex Chen',
            },
            {
              text: 'A neighbor',
              speaker: 'SPEAKER_100',
              isUser: false,
              start: 2,
              end: 3,
            },
            {
              text: 'Your turn',
              speaker: 'SPEAKER_00',
              isUser: true,
              start: 4,
              end: 5,
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
  expect(copy).toContain('omi  ·  Omi said this');
  expect(copy).toContain('Speaker 2  ·  A neighbor');
  expect(copy).toContain('You  ·  Your turn');
  expect(copy).not.toContain('Speaker 1  ·  Omi said this');
  expect(copy).not.toContain('Speaker 100');
  expect(copy).not.toContain('Alex Chen  ·  Omi said this');
});

test('legacy conversation details name a failed GET people instead of empty success', () => {
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
        actionItems: [],
        peopleError: desktopBackendServiceCopy,
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Hello there',
              speaker: 'SPEAKER_00',
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
  expect(copy).toContain('People');
  expect(copy).toContain(desktopBackendServiceCopy);
  expect(copy).toContain('Speaker 1  ·  Hello there');
  expect(copy).not.toContain('Alex Chen');
  expect(copy).not.toContain('person-alex');
});

test('legacy conversation details name Flutter TranscriptWidget empty GET translations', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Hello there',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1,
              translations: ['\u0085'],
            },
          ],
        },
      },
    },
    reload: jest.fn(),
  });
  const view = render({
    apiContract: 'omi',
    conversation: {...conversation, id: 'old-1'},
  });
  const copy = text(view);
  const whitespaceTranslations = view.root.findAll(node => {
    if (node.type !== Text) {
      return false;
    }
    const children = node.props.children;
    return (
      children === '\u0085' ||
      (Array.isArray(children) && children.some(child => child === '\u0085'))
    );
  });
  expect(whitespaceTranslations.length).toBeGreaterThan(0);
  expect(copy).toContain('Hello there');
  expect(copy).toContain('\u0085');
  expect(copy).toContain('translated by omi');
});

test('legacy conversation details name GET transcript translations without a notice dialog', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Hello there',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1,
              translations: ['Hola alli'],
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
  expect(copy).toContain('Hello there');
  expect(copy).toContain('Hola alli');
  expect(copy).toContain('translated by omi');
});

test('legacy conversation details name GET stt_provider unknown as Flutter Omi', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Hello there',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1,
              sttProvider: 'Deepgram',
            },
            {
              text: 'Next line',
              speaker: 'SPEAKER_01',
              isUser: false,
              start: 1,
              end: 2,
              sttProvider: transcriptSttOmiFallbackCopy(),
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
  expect(copy).toContain('Deepgram');
  expect(copy).toContain(transcriptSttOmiFallbackCopy());
});

test('legacy conversation details name Flutter Unknown for empty GET stt_provider', () => {
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
        actionItems: [],
        transcript: {
          status: 'loaded',
          segments: [
            {
              text: 'Hello there',
              speaker: 'SPEAKER_00',
              isUser: false,
              start: 0,
              end: 1,
              sttProvider: transcriptSttUnknownCopy(),
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
  expect(copy).toContain(transcriptSttUnknownCopy());
  expect(copy).not.toContain('Omi');
});
