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
          memories: [{title: 'Morning standup', emoji: '🚀'}],
          evidence: [{title: 'Calendar', detail: 'Tuesday agenda'}],
          contentBlocks: [
            {
              eyebrow: 'Discovery',
              title: 'Quiet mornings',
              detail: 'You like a slow start.',
            },
            {eyebrow: 'Memory', title: 'Prefers concise notes'},
          ],
        },
        {
          id: 'human-1',
          sender: 'human',
          text: 'Save this.',
          createdAt: Date.parse('2026-09-07T12:01:00.000Z'),
          generationOutcome: null,
          appName: 'Notes',
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
  expect(tree).toContain('Save this.');
  expect(tree).not.toContain('Open in Memories');
  expect(tree).not.toContain('Open conversation');
  expect(tree).not.toContain('Open in Goals');
  expect(tree).not.toContain('Show more');
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
  expect(copy).toContain('The transcript is empty.');
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
  expect(copy).toContain('Started ·');
  expect(copy).toContain('In progress');
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('Duration unavailable');
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
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {
        ...conversation,
        id: 'old-1',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:05:00.000Z',
        status: 'completed',
        discarded: true,
      },
    }),
  );
  expect(copy).toContain('Started ·');
  expect(copy).toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('Duration unavailable');
  expect(copy).toContain('Status ·');
  expect(copy).toContain('Completed');
  expect(copy).toContain('Locked');
  expect(copy).toContain('Discarded');
  expect(copy).not.toContain('in_progress');
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
  expect(missingStart).toContain('Started ·');
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
  expect(copy).toContain('Duration ·');
  expect(copy).toContain('2 mins 30 secs');
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
  expect(copy).toContain('Started ·');
  expect(copy).toContain('Status ·');
  expect(copy).toContain('In progress');
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
  expect(copy).toContain('Call Alex');
  expect(copy).toContain('Send notes');
  expect(copy).toContain('Completed');
  expect(copy).not.toContain('in_progress');
});

test('legacy conversation details omit empty or whitespace action items', () => {
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
  const copy = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1'},
    }),
  );
  expect(copy).not.toContain('Action Items');
  expect(copy).not.toContain('\u0085');
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
  expect(copy).toContain('Notes');
  expect(copy).not.toContain('Unknown App');
  const discarded = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', discarded: true},
    }),
  );
  expect(discarded).not.toContain('App wrote this recap');
  expect(discarded).not.toContain('Notes');
});

test('conversation details name GET shared or public visibility and omit private', () => {
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
  expect(published).toContain('Public');
  const hidden = text(
    render({
      apiContract: 'omi',
      conversation: {...conversation, id: 'old-1', visibility: 'private'},
    }),
  );
  expect(hidden).not.toContain('Shared');
  expect(hidden).not.toContain('Public');
  expect(hidden).not.toContain('Private');
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

test('legacy conversation details name GET photo counts and captions', () => {
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
  expect(copy).toContain('3 photos');
  expect(copy).toContain('Whiteboard notes');
});

test('legacy conversation details name GET folder name and omit unresolved folders', () => {
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
  expect(omitted).not.toContain('No folder');
  expect(omitted).not.toContain('folder-work');
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
