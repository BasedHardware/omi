import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {ConversationsPage} from './Conversations';
import {
  clockLabel,
  conversationStatusCopy,
  desktopBackendUnavailableCopy,
  type ConversationProjection,
} from '../desktopReadClient';
import {
  calendarCaptureGapSpan,
  captureGapTimeRangeCopy,
} from '../legacyOmiCalendarCaptureGaps';

function textOf(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAllByType(Text)
    .flatMap(node =>
      Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children],
    )
    .filter(
      (value): value is string | number =>
        typeof value === 'string' || typeof value === 'number',
    )
    .join(' ');
}

const incompletePage = {
  windowStatus: 'incomplete' as const,
  complete: false,
  hasMore: false,
  nextCursor: null,
  completenessStatus: 'incomplete' as const,
  reasons: ['accepted_work_pending'],
};

test('conversation grant denial shows the typed error instead of an empty library', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'error',
          error: 'This saved data is not available for this account.',
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(renderer)).toContain(
    'This saved data is not available for this account.',
  );
  expect(textOf(renderer)).not.toContain('No conversations yet.');
  expect(textOf(renderer)).not.toContain('Conversations could not be loaded.');
});

test('incomplete empty conversations do not claim a complete library', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {items: [], page: incompletePage},
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(renderer)).toContain('Conversations are incomplete.');
  expect(textOf(renderer)).not.toContain('No conversations yet.');
});

test('an incomplete empty conversation search does not claim a complete miss', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {items: [], page: incompletePage},
        }}
        loading={false}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      )
      .props.onChangeText('nomatch');
  });
  expect(textOf(renderer)).toContain('Conversations are incomplete.');
  expect(textOf(renderer)).not.toContain('No loaded conversations match.');
});

test('complete empty conversations may claim emptiness', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {
            items: [],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(renderer)).toContain('No conversations yet.');
  expect(textOf(renderer)).not.toContain('Conversations are incomplete.');
});

test('untitled processing conversations stay visible instead of a blank row', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:processing-one',
    title: '',
    summary: '',
    searchableText:
      'Processing conversation…\nConversation summary is not ready yet.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'processing',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(renderer)).toContain('Processing conversation…');
  expect(textOf(renderer)).toContain('Conversation summary is not ready yet.');
  expect(textOf(renderer)).not.toContain('No conversations yet.');
});

test('untitled conversations keep overview speech on the open control', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:title-ai',
    title: '',
    summary: 'Assistant words',
    searchableText: 'Conversation title unavailable\nAssistant words',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'in_progress',
    source: 'chat',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(renderer)).toContain('Conversation title unavailable');
  expect(textOf(renderer)).toContain('Assistant words');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Open conversation Assistant words',
    ).length,
  ).toBeGreaterThan(0);
});

test('listen conversations keep list overview speech on the open control', () => {
  const title = 'a'.repeat(80);
  const summary = `${title} later speech`;
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'conversation-one',
    title,
    summary,
    searchableText: `${title}\n${summary}`,
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(renderer)).toContain(title);
  expect(textOf(renderer)).toContain(summary);
  expect(
    renderer.root.findAll(
      node => node.props.numberOfLines === 3 && node.props.children === summary,
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === `Open conversation ${summary}`,
    ).length,
  ).toBeGreaterThan(0);
});

test('a NEXT LINE-only conversation search keeps rows instead of claiming a miss', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:processing-one',
    title: '',
    summary: '',
    searchableText:
      'Processing conversation…\nConversation summary is not ready yet.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'processing',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      )
      .props.onChangeText('\u0085');
  });
  expect(textOf(renderer)).toContain('Processing conversation…');
  expect(textOf(renderer)).not.toContain('No loaded conversations match.');
  expect(textOf(renderer)).not.toContain('\u0085');
});

test('listen conversations do not present a blank detail as a transcript', async () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:completed-one',
    title: 'Walked to the market',
    summary: 'A short overview of the walk.',
    searchableText: 'Walked to the market\nA short overview of the walk.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  try {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <ConversationsPage
          outcome={{
            status: 'success',
            value: {
              items: [item],
              page: {
                ...incompletePage,
                windowStatus: 'complete',
                complete: true,
                completenessStatus: 'complete',
                reasons: [],
              },
            },
          }}
          loading={false}
        />,
      );
    });
    await act(async () =>
      renderer.root
        .findAll(
          node =>
            node.props.accessibilityLabel ===
            'Open conversation Walked to the market',
        )[0]!
        .props.onPress(),
    );
    expect(textOf(renderer)).toContain(
      'A full transcript is not available for this conversation yet.',
    );
    expect(textOf(renderer)).toContain('A short overview of the walk.');
    expect(textOf(renderer)).not.toContain('Transcript');
    expect(textOf(renderer)).not.toContain('Messages');
  } finally {
    dimensions.mockRestore();
  }
});

test('nested non-retryable conversation reads omit Refresh', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'error',
          error: desktopBackendUnavailableCopy,
        }}
        loading={false}
        onRefresh={jest.fn()}
      />,
    );
  });
  expect(textOf(renderer)).toContain(desktopBackendUnavailableCopy);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh conversations',
    ),
  ).toHaveLength(0);
});

test('retryable conversation reads still offer Refresh', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'error',
          error:
            'This saved data could not be loaded. Retry without changing it.',
        }}
        loading={false}
        onRefresh={jest.fn()}
      />,
    );
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh conversations',
    ).length,
  ).toBeGreaterThan(0);
});

test('nested non-retryable later conversation pages do not claim more are available in an empty search', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:processing-one',
    title: 'Processing conversation…',
    summary: 'Conversation summary is not ready yet.',
    searchableText:
      'Processing conversation…\nConversation summary is not ready yet.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'processing',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              windowStatus: 'more',
              complete: false,
              hasMore: true,
              nextCursor: 'conversations-next',
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
        notice={desktopBackendUnavailableCopy}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      )
      .props.onChangeText('nomatch');
  });
  expect(textOf(renderer)).toContain('No loaded conversations match.');
  expect(textOf(renderer)).toContain(desktopBackendUnavailableCopy);
  expect(textOf(renderer)).not.toContain('More conversations are available.');
});

test('a requested conversation id opens compact conversation detail', () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
  const consumed = jest.fn();
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'recording:recap-one',
    title: 'Walked to the market',
    summary: 'A short overview of the walk.',
    searchableText: 'Walked to the market\nA short overview of the walk.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  try {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      renderer = ReactTestRenderer.create(
        <ConversationsPage
          loading={false}
          onRequestedConversationConsumed={consumed}
          outcome={{
            status: 'success',
            value: {
              items: [item],
              page: {
                ...incompletePage,
                windowStatus: 'complete',
                complete: true,
                completenessStatus: 'complete',
                reasons: [],
              },
            },
          }}
          requestedConversationId={item.id}
        />,
      );
    });
    expect(textOf(renderer)).toContain('Walked to the market');
    expect(textOf(renderer)).toContain('Back to conversations');
    expect(consumed).toHaveBeenCalledTimes(1);
    expect(
      renderer.root.findAll(
        node =>
          node.props.accessibilityLabel ===
          'Open conversation Walked to the market',
      ),
    ).toHaveLength(0);
  } finally {
    dimensions.mockRestore();
  }
});

test('conversation list and detail date older days instead of month and day only', () => {
  const older = new Date(2025, 7, 10, 12, 0);
  const expected = clockLabel(older.getTime(), Date.now());
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:older-one',
    title: 'Product review',
    summary: 'Talked through the release.',
    searchableText: 'Product review\nTalked through the release.',
    createdAt: older.toISOString(),
    updatedAt: older.toISOString(),
    startedAt: older.toISOString(),
    finishedAt: older.toISOString(),
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(renderer)).toContain(expected);
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Product review',
      )
      .props.onPress();
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Started ·');
  expect(copy).toContain('Finished ·');
  expect(copy).toContain(expected);
  expect(expected).toContain(
    older.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }),
  );
});

test('conversation durations under a minute do not claim 0 min', () => {
  const startedAt = '2026-09-07T12:00:00.000Z';
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:short-one',
    title: 'Quick note',
    summary: 'Twenty seconds.',
    searchableText: 'Quick note\nTwenty seconds.',
    createdAt: startedAt,
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt,
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  const page = {
    status: 'success' as const,
    value: {
      items: [item],
      page: {
        ...incompletePage,
        windowStatus: 'complete' as const,
        complete: true,
        completenessStatus: 'complete' as const,
        reasons: [],
      },
    },
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage outcome={page} loading={false} />,
    );
  });
  expect(textOf(renderer)).toContain('< 1 min');
  expect(textOf(renderer)).not.toContain('0 min');
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Quick note',
      )
      .props.onPress();
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Duration ·');
  expect(copy).toContain('< 1 min');
  expect(copy).not.toContain('0 min');
});

test('a zero conversation start time does not invent a duration', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:epoch-duration',
    title: 'Missing start',
    summary: 'Finished without a real start time.',
    searchableText: 'Missing start\nFinished without a real start time.',
    createdAt: new Date(0).toISOString(),
    updatedAt: '2026-09-07T12:00:00.000Z',
    startedAt: new Date(0).toISOString(),
    finishedAt: '2026-09-07T12:00:00.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  expect(textOf(renderer)).toContain('Duration unavailable');
  expect(textOf(renderer)).not.toContain('hr');
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Missing start',
      )
      .props.onPress();
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Duration ·');
  expect(copy).toContain('Duration unavailable');
  expect(copy).not.toContain('hr');
});

test('conversation capture time uses the same clock as Started and not 1970', () => {
  const older = new Date(2025, 7, 10, 12, 0);
  const expected = clockLabel(older.getTime(), Date.now());
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:captured-one',
    title: 'Device capture',
    summary: 'Recorded on the wearable.',
    searchableText: 'Device capture\nRecorded on the wearable.',
    createdAt: older.toISOString(),
    updatedAt: older.toISOString(),
    startedAt: older.toISOString(),
    finishedAt: older.toISOString(),
    capturedAtMs: older.getTime(),
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Device capture',
      )
      .props.onPress();
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Captured (device time)');
  expect(copy).toContain(expected);
  expect(copy).not.toContain('1970');
});

test('conversation list stars only when the backend marked the row starred', () => {
  const base = {
    kind: 'conversation' as const,
    summary: 'Kept for later.',
    searchableText: 'Kept for later.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    status: 'completed',
    source: 'listen',
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...base,
                id: 'listen:open-one',
                title: 'Open note',
                searchableText: 'Open note\nKept for later.',
                starred: false,
              },
              {
                ...base,
                id: 'listen:kept-one',
                title: 'Kept note',
                searchableText: 'Kept note\nKept for later.',
                starred: true,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  const copy = textOf(renderer);
  expect(copy).toContain('★');
  expect(copy).not.toContain('☆');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Starred conversation',
    ),
  ).toBeTruthy();
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Not starred',
    ),
  ).toEqual([]);
});

test('conversation detail status is not a raw wire token', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:in-progress-one',
    title: 'Morning standup',
    summary: 'Still processing this recording.',
    searchableText: 'Morning standup\nStill processing this recording.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'in_progress',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  expect(textOf(renderer)).not.toContain('Duration unavailable');
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Morning standup',
      )
      .props.onPress();
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Status ·');
  expect(copy).toContain(conversationStatusCopy('in_progress'));
  expect(copy).not.toContain('in_progress');
  expect(copy).not.toContain('Finished ·');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('Duration unavailable');
});

test('whitespace conversation detail status is not a blank row', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:blank-status-one',
    title: 'Morning standup',
    summary: 'Still processing this recording.',
    searchableText: 'Morning standup\nStill processing this recording.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: ' \t\n',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Morning standup',
      )
      .props.onPress();
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Status ·');
  expect(copy).toContain('Status unavailable');
  expect(copy).not.toContain(' \t\n');
});

test('a zero conversation createdAt groups as Date unavailable instead of 1970', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:epoch-one',
    title: 'Undated recording',
    summary: 'Missing a real start time.',
    searchableText: 'Undated recording\nMissing a real start time.',
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
    startedAt: null,
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Date unavailable');
  expect(copy).toContain('Time unavailable');
  expect(copy).not.toContain('1970');
});

test('conversation list names GET capture time without inventing it on untimed rows', () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
  const captured = new Date(2025, 7, 10, 12, 0);
  const expected = `Captured (device time) · ${clockLabel(
    captured.getTime(),
    Date.now(),
  )}`;
  const base = {
    kind: 'conversation' as const,
    title: 'Device capture',
    summary: 'Recorded on the wearable.',
    searchableText: 'Device capture\nRecorded on the wearable.',
    createdAt: captured.toISOString(),
    updatedAt: captured.toISOString(),
    startedAt: captured.toISOString(),
    finishedAt: captured.toISOString(),
    starred: false,
    status: 'completed' as const,
    source: 'omi' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  try {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      renderer = ReactTestRenderer.create(
        <ConversationsPage
          loading={false}
          outcome={{
            status: 'success',
            value: {
              items: [
                {
                  ...base,
                  id: 'recording:captured-one',
                  capturedAtMs: captured.getTime(),
                },
                {
                  ...base,
                  id: 'recording:plain-one',
                  title: 'Untimed recording',
                  searchableText:
                    'Untimed recording\nRecorded on the wearable.',
                },
              ],
              page: {
                ...incompletePage,
                windowStatus: 'complete',
                complete: true,
                completenessStatus: 'complete',
                reasons: [],
              },
            },
          }}
        />,
      );
    });
    const copy = textOf(renderer);
    expect(copy).toContain(expected);
    expect(copy).toContain('Untimed recording');
    expect(copy).not.toContain('1970');
    expect((copy.match(/Captured \(device time\)/g) ?? []).length).toBe(1);
  } finally {
    dimensions.mockRestore();
  }
});

test('conversation list names locked and discarded conversations without empty badges', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Kept recording',
    summary: 'Saved words',
    searchableText: 'Kept recording\nSaved words',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'processing',
    source: 'listen' as const,
    visibility: 'private' as const,
    folderId: null,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...base,
                id: 'listen:locked-one',
                locked: true,
                discarded: true,
              },
              {
                ...base,
                id: 'listen:open-one',
                title: 'Open recording',
                searchableText: 'Open recording\nSaved words',
                status: 'completed',
                locked: false,
                discarded: false,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Locked');
  expect(copy).toContain('Discarded');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Locked conversation',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Discarded conversation',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Not locked',
    ),
  ).toHaveLength(0);
});

test('conversation list names failed conversations without Status on every row', () => {
  const base = {
    kind: 'conversation' as const,
    title: '',
    summary: '',
    searchableText: '',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    source: 'listen' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...base,
                id: 'recording:failed-one',
                status: 'failed',
              },
              {
                ...base,
                id: 'chat:chat-main',
                title: 'Hello',
                searchableText: 'Hello',
                status: 'in_progress',
                source: 'chat' as const,
                finishedAt: null,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Conversation title unavailable');
  expect(copy).toContain('Failed');
  expect(copy).toContain('Hello');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Failed conversation',
    ).length,
  ).toBeGreaterThan(0);
  expect(copy).not.toContain(conversationStatusCopy('in_progress'));
});

test('conversation list names processing conversations without Status on every row', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    source: 'listen' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...base,
                id: 'recording:processing-one',
                status: 'processing',
              },
              {
                ...base,
                id: 'recording:merging-one',
                title: 'Standup recap',
                searchableText: 'Standup recap\nNotes',
                status: 'merging',
              },
              {
                ...base,
                id: 'chat:chat-main',
                title: 'Hello',
                searchableText: 'Hello',
                status: 'in_progress',
                source: 'chat' as const,
                finishedAt: null,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Morning standup');
  expect(copy).toContain('Standup recap');
  expect(copy).toContain('Hello');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Processing conversation',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Processing conversation' &&
        node.props.children === 'Processing',
    ).length,
  ).toBeGreaterThan(0);
  expect(copy).not.toContain(conversationStatusCopy('in_progress'));
  expect(copy).not.toContain(conversationStatusCopy('merging'));
});

test('conversation list names GET emoji and omits it when discarded or empty', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {...base, id: 'omi-emoji', emoji: '🚀'},
              {
                ...base,
                id: 'omi-discarded',
                title: 'Discarded talk',
                discarded: true,
                emoji: '🧠',
              },
              {...base, id: 'omi-empty', title: 'No emoji', emoji: ' \u0085 '},
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  expect(textOf(renderer)).toContain('🚀');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Conversation emoji',
    ).length,
  ).toBeGreaterThan(0);
  expect(textOf(renderer)).not.toContain('🧠');
  expect(textOf(renderer)).not.toContain('\u0085');
});

test('conversation list names Flutter New chrome for a just-created row', () => {
  const now = Date.now();
  const base = {
    kind: 'conversation' as const,
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    updatedAt: new Date(now - 30_000).toISOString(),
    startedAt: new Date(now - 30_000).toISOString(),
    starred: false,
    status: 'completed' as const,
    source: 'omi' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...base,
                id: 'omi-new',
                createdAt: new Date(now - 30_000).toISOString(),
                finishedAt: null,
              },
              {
                ...base,
                id: 'omi-old',
                title: 'Older talk',
                createdAt: '2026-09-07T00:00:00.000Z',
                finishedAt: '2026-09-07T00:01:00.000Z',
                startedAt: '2026-09-07T00:00:00.000Z',
                updatedAt: '2026-09-07T00:01:00.000Z',
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  expect(textOf(renderer)).toContain('New 🚀');
  expect(textOf(renderer)).toContain('Older talk');
});

test('conversation list names GET category and omits it when discarded or empty', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {...base, id: 'omi-work', category: 'work'},
              {
                ...base,
                id: 'omi-discarded',
                title: 'Discarded talk',
                discarded: true,
                category: 'work',
              },
              {
                ...base,
                id: 'omi-empty',
                title: 'No category',
                category: ' \u0085 ',
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  expect(textOf(renderer)).toContain('Work');
  expect(textOf(renderer)).not.toContain('work');
});

test('conversation list names GET source remaps and omits ordinary sources', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...base,
                id: 'omi-screenpipe',
                source: 'screenpipe',
                category: 'work',
              },
              {
                ...base,
                id: 'omi-glass',
                title: 'Glass talk',
                source: 'openglass',
              },
              {
                ...base,
                id: 'omi-sdcard',
                title: 'Card talk',
                source: 'sdcard',
                discarded: true,
              },
              {
                ...base,
                id: 'omi-rayban',
                title: 'Ray talk',
                source: 'rayban_meta',
              },
              {
                ...base,
                id: 'omi-phone',
                title: 'Phone talk',
                source: 'phone',
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Screenpipe');
  expect(copy).toContain('OmiGlass');
  expect(copy).toContain('SD Card');
  expect(copy).toContain('Ray-Ban Meta');
  expect(copy).not.toContain('Work');
  expect(copy).not.toContain('phone');
  expect(copy).not.toContain('omi');
});

test('conversation list names discarded GET photo counts and omits them otherwise', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi' as const,
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...base,
                id: 'omi-photos',
                discarded: true,
                photoCount: 2,
              },
              {...base, id: 'omi-kept', photoCount: 3},
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
      />,
    );
  });
  expect(textOf(renderer)).toContain('2 photos');
  expect(textOf(renderer)).not.toContain('3 photos');
});

test('conversation list names GET goals without add or a write sheet', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'goal-read',
            title: 'Read 20 books',
            current_value: 3,
            target_value: 10,
          },
          {id: 'goal-empty', title: ' \t', current_value: 1, target_value: 2},
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {
            items: [],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = textOf(renderer);
  expect(tree).toContain('Goals');
  expect(tree).toContain('Read 20 books');
  expect(tree).toContain('3/10');
  expect(tree).toContain('No conversations yet.');
  expect(tree).not.toContain('goal-read');
  expect(tree).not.toContain('No goals');
  expect(tree).not.toContain('🎯');
  expect(tree).not.toContain('Add');
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/goals/all',
  });
  expect(request.mock.calls.some(call => call[0].method === 'PATCH')).toBe(
    false,
  );
  expect(request.mock.calls.some(call => call[0].path === '/v1/goals')).toBe(
    false,
  );
});

test('conversation list omits GET goals on failure and while searching', async () => {
  let goalsResponse: {status: number; body: string | null} = {
    status: 404,
    body: null,
  };
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      return {
        id: request.id,
        status: goalsResponse.status,
        body: goalsResponse.body,
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                kind: 'conversation',
                id: 'chat:one',
                title: 'Standup',
                summary: 'Notes',
                searchableText: 'Standup\nNotes',
                createdAt: '2026-09-07T00:00:00.000Z',
                updatedAt: '2026-09-07T00:01:00.000Z',
                startedAt: '2026-09-07T00:00:00.000Z',
                finishedAt: null,
                starred: false,
                status: 'in_progress',
                source: 'chat',
                visibility: 'private',
                folderId: null,
                locked: false,
                discarded: false,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(textOf(renderer)).not.toContain('Goals');
  expect(textOf(renderer)).not.toContain('No goals');

  goalsResponse = {
    status: 200,
    body: JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
    ]),
  };
  await act(async () => {
    renderer.update(
      <ConversationsPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                kind: 'conversation',
                id: 'chat:one',
                title: 'Standup',
                summary: 'Notes',
                searchableText: 'Standup\nNotes',
                createdAt: '2026-09-07T00:00:00.000Z',
                updatedAt: '2026-09-07T00:01:00.000Z',
                startedAt: '2026-09-07T00:00:00.000Z',
                finishedAt: null,
                starred: false,
                status: 'in_progress',
                source: 'chat',
                visibility: 'private',
                folderId: null,
                locked: false,
                discarded: false,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(textOf(renderer)).toContain('Goals');
  expect(textOf(renderer)).toContain('Read 20 books');
  const search = renderer.root.findByProps({
    accessibilityLabel: 'Search loaded conversations',
  });
  await act(async () => {
    search.props.onChangeText('Standup');
  });
  expect(textOf(renderer)).not.toContain('Goals');
  expect(textOf(renderer)).not.toContain('Read 20 books');
  expect(textOf(renderer)).toContain('Standup');
});

test('conversation list names GET folders without add or a write sheet', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'folder-work', name: 'Work'},
          {id: 'folder-empty', name: ' \t'},
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const item = {
    kind: 'conversation' as const,
    summary: 'Notes',
    searchableText: 'Notes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'in_progress' as const,
    source: 'chat' as const,
    visibility: 'private' as const,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...item,
                id: 'chat:work',
                title: 'Work standup',
                searchableText: 'Work standup\nNotes',
                folderId: 'folder-work',
              },
              {
                ...item,
                id: 'chat:inbox',
                title: 'Inbox chat',
                searchableText: 'Inbox chat\nNotes',
                folderId: null,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = textOf(renderer);
  expect(tree).toContain('Work');
  expect(tree).toContain('Work standup');
  expect(tree).toContain('Inbox chat');
  expect(tree).not.toContain('folder-work');
  expect(tree).not.toContain('folder-empty');
  expect(tree).not.toContain('Add');
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/folders',
  });
  expect(
    request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'PATCH',
    ),
  ).toBe(false);
  await act(async () => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Show Work conversations',
      )
      .props.onPress();
  });
  expect(textOf(renderer)).toContain('Work standup');
  expect(textOf(renderer)).not.toContain('Inbox chat');
  await act(async () => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Show Work conversations',
      )
      .props.onPress();
  });
  expect(textOf(renderer)).toContain('Work standup');
  expect(textOf(renderer)).toContain('Inbox chat');
});

test('conversation list names GET calendar capture gaps without a write sheet', async () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:work',
    title: 'Work chat',
    summary: 'Notes',
    searchableText: 'Work chat\nNotes',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:01:00.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'in_progress',
    source: 'chat',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  const span = calendarCaptureGapSpan([item]);
  const request = jest.fn(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/calendar/capture-gaps?')
    ) {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            event_id: 'event-design',
            title: 'Design review',
            start_time: '2026-09-07T15:00:00.000Z',
            end_time: '2026-09-07T16:30:00.000Z',
            coverage: 'not_captured',
          },
          {
            event_id: 'event-empty',
            title: ' \t',
            start_time: '2026-09-07T17:00:00.000Z',
            end_time: '2026-09-07T18:00:00.000Z',
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {
            items: [item],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = textOf(renderer);
  expect(tree).toContain('Not captured (1)');
  expect(tree).toContain('Design review');
  expect(tree).toContain(
    captureGapTimeRangeCopy(
      Date.parse('2026-09-07T15:00:00.000Z'),
      Date.parse('2026-09-07T16:30:00.000Z'),
    ),
  );
  expect(tree).toContain('Work chat');
  expect(tree).not.toContain('event-design');
  expect(tree).not.toContain('event-empty');
  expect(tree).not.toContain('not_captured');
  expect(tree).not.toContain('html_link');
  expect(tree).not.toContain('Add');
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/calendar/capture-gaps?start=${encodeURIComponent(
      span?.start ?? '',
    )}&end=${encodeURIComponent(span?.end ?? '')}`,
  });
  expect(
    request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'PATCH',
    ),
  ).toBe(false);
  const search = renderer.root.findByProps({
    accessibilityLabel: 'Search loaded conversations',
  });
  await act(async () => {
    search.props.onChangeText('Work');
  });
  expect(textOf(renderer)).toContain('Work chat');
  expect(textOf(renderer)).not.toContain('Not captured (1)');
  expect(textOf(renderer)).not.toContain('Design review');
  await act(async () => {
    search.props.onChangeText('');
  });
  expect(textOf(renderer)).toContain('Design review');
  await act(async () => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Show starred conversations',
      )
      .props.onPress();
  });
  expect(textOf(renderer)).not.toContain('Design review');
});

test('conversation list omits GET calendar capture gaps on failure and empty libraries', async () => {
  const request = jest.fn(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/calendar/capture-gaps?')
    ) {
      return {id: request.id, status: 400, body: '[]'};
    }
    return {id: request.id, status: 404, body: null};
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {
            items: [],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(textOf(renderer)).toContain('No conversations yet.');
  expect(textOf(renderer)).not.toContain('Not captured');
  expect(
    request.mock.calls.some(
      call =>
        typeof call[0].path === 'string' &&
        call[0].path.startsWith('/v1/calendar/capture-gaps?'),
    ),
  ).toBe(false);
  await act(async () => {
    renderer.update(
      <ConversationsPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                kind: 'conversation',
                id: 'chat:one',
                title: 'Standup',
                summary: 'Notes',
                searchableText: 'Standup\nNotes',
                createdAt: '2026-09-07T12:00:00.000Z',
                updatedAt: '2026-09-07T12:01:00.000Z',
                startedAt: '2026-09-07T12:00:00.000Z',
                finishedAt: null,
                starred: false,
                status: 'in_progress',
                source: 'chat',
                visibility: 'private',
                folderId: null,
                locked: false,
                discarded: false,
              },
            ],
            page: {
              ...incompletePage,
              windowStatus: 'complete',
              complete: true,
              completenessStatus: 'complete',
              reasons: [],
            },
          },
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(textOf(renderer)).toContain('Standup');
  expect(textOf(renderer)).not.toContain('Not captured');
  expect(
    request.mock.calls.some(
      call =>
        typeof call[0].path === 'string' &&
        call[0].path.startsWith('/v1/calendar/capture-gaps?'),
    ),
  ).toBe(true);
});

