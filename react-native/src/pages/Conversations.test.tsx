import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {ConversationsPage} from './Conversations';
import {
  clockLabel,
  conversationDetailDateChipCopy,
  conversationStatusCopy,
  conversationStructuredEmojiDefaultCopy,
  conversationsEmptyCopy,
  conversationsStarredEmptyCopy,
  desktopBackendServiceCopy,
  desktopBackendUnavailableCopy,
  desktopReadErrorCopy,
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
  expect(textOf(renderer)).not.toContain(conversationsEmptyCopy());
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
  expect(textOf(renderer)).not.toContain(conversationsEmptyCopy());
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
  expect(textOf(renderer)).toContain(conversationsEmptyCopy());
  expect(textOf(renderer)).not.toContain('No conversations yet.');
  expect(textOf(renderer)).not.toContain('Conversations are incomplete.');
  expect(textOf(renderer)).toContain(
    'Conversations you record show up here. Tap a tile on the home tab to start your first one.',
  );
});

test('starred filter names Flutter noStarredConversations instead of generic match copy', () => {
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
    status: 'completed',
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
  expect(textOf(renderer)).toContain('Work chat');
  expect(textOf(renderer)).not.toContain(conversationsStarredEmptyCopy());
  act(() => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Show starred conversations',
      )
      .props.onPress();
  });
  const tree = textOf(renderer);
  expect(tree).toContain(conversationsStarredEmptyCopy());
  expect(tree).not.toContain('Work chat');
  expect(tree).not.toContain('No loaded conversations match.');
  expect(tree).not.toContain(conversationsEmptyCopy());
  expect(tree).not.toContain('No conversations yet.');
  expect(tree).toContain(
    'To star a conversation, open it and tap the star icon in the header.',
  );
  expect(tree).not.toContain(
    'Search and filters cover conversations already loaded on this device.',
  );
});

test('folder filter names Flutter EmptyConversationsWidget instead of generic match copy', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([{id: 'folder-work', name: 'Work'}]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:inbox',
    title: 'Inbox chat',
    summary: 'Notes',
    searchableText: 'Inbox chat\nNotes',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:01:00.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'chat',
    visibility: 'private',
    folderId: null,
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
  });
  expect(textOf(renderer)).toContain('Inbox chat');
  await act(async () => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Show Work conversations',
      )
      .props.onPress();
  });
  const tree = textOf(renderer);
  expect(tree).toContain('No conversations yet');
  expect(tree).not.toContain('Inbox chat');
  expect(tree).not.toContain('No loaded conversations match.');
  expect(tree).not.toContain(conversationsEmptyCopy());
  expect(tree).not.toContain(
    'Conversations you record show up here. Tap a tile on the home tab to start your first one.',
  );
  expect(tree).not.toContain(conversationsStarredEmptyCopy());
  expect(tree).not.toContain(
    'Search and filters cover conversations already loaded on this device.',
  );
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
  expect(textOf(renderer)).not.toContain('Processing conversation…');
  expect(textOf(renderer)).not.toContain(
    'Conversation summary is not ready yet.',
  );
  expect(textOf(renderer)).toContain('Sep 07');
  expect(textOf(renderer)).toContain('1m');
  expect(textOf(renderer)).not.toContain(conversationsEmptyCopy());
  expect(textOf(renderer)).not.toContain('No conversations yet.');
});

test('conversation search does not match invented empty-overview copy', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:empty-overview',
    title: 'Morning standup',
    summary: '',
    searchableText: 'Morning standup\n',
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
  expect(textOf(renderer)).toContain('Morning standup');
  act(() => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      )
      .props.onChangeText('unavailable');
  });
  expect(textOf(renderer)).not.toContain('Conversation summary unavailable');
  expect(textOf(renderer)).not.toContain(
    'Conversation summary is not ready yet.',
  );
  expect(textOf(renderer)).toContain('No loaded conversations match.');
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
  expect(textOf(renderer)).not.toContain('Conversation title unavailable');
  expect(textOf(renderer)).not.toContain('Assistant words');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Open conversation Assistant words',
    ).length,
  ).toBeGreaterThan(0);
});

test('conversation list names Flutter ConversationListItem padded GET title instead of remapping to overview', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:title-ai',
    title: '\u0085',
    summary: 'Assistant words',
    searchableText: '\u0085\nAssistant words',
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
  expect(textOf(renderer)).toContain('\u0085');
  expect(textOf(renderer)).not.toContain('Assistant words');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Open conversation \u0085',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Open conversation Assistant words',
    ).length,
  ).toBe(0);
});

test('conversation list names Flutter ConversationListItem padded GET title instead of remapping listen overview', () => {
  const title = `  ${'a'.repeat(80)}  `;
  const summary = `${'a'.repeat(80)} later speech`;
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
  expect(textOf(renderer)).not.toContain(summary);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === `Open conversation ${title}`,
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === `Open conversation ${summary}`,
    ).length,
  ).toBe(0);
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
  expect(textOf(renderer)).not.toContain('Processing conversation…');
  expect(textOf(renderer)).not.toContain('No loaded conversations match.');
  expect(textOf(renderer)).not.toContain('\u0085');
  expect(textOf(renderer)).toContain('Sep 07');
  expect(textOf(renderer)).toContain('1m');
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

test('conversation list names Flutter DateListItem time and omits dated row clocks', () => {
  const older = new Date(2025, 7, 10, 12, 0);
  const time = older.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
  const group = older.toLocaleDateString(undefined, {
    month: 'short',
    day: '2-digit',
  });
  const dated = clockLabel(older.getTime(), Date.now());
  const chip = conversationDetailDateChipCopy(older.toISOString(), Date.now());
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
  const list = textOf(renderer);
  expect(list).toContain(time);
  expect(list).toContain(group);
  expect(list).not.toContain(dated);
  expect(list).not.toContain('Today');
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Product review',
      )
      .props.onPress();
  });
  const copy = textOf(renderer);
  expect(copy).not.toContain('Started ·');
  expect(copy).not.toContain('Finished ·');
  expect(copy).toContain(chip);
  expect(copy).not.toContain(dated);
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
  expect(textOf(renderer)).toContain('20s');
  expect(textOf(renderer)).not.toContain('< 1 min');
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
  expect(copy).toContain('20s');
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('< 1 min');
  expect(copy).not.toContain('0 min');
});

test('same-second conversation clocks omit compact duration like Flutter list', () => {
  const startedAt = '2026-09-07T12:00:00.000Z';
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:zero-span',
    title: 'Instant note',
    summary: 'Finished in the same second.',
    searchableText: 'Instant note\nFinished in the same second.',
    createdAt: startedAt,
    updatedAt: startedAt,
    startedAt,
    finishedAt: startedAt,
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
  expect(textOf(renderer)).not.toContain('Duration unavailable');
  expect(textOf(renderer)).not.toContain('0s');
  expect(textOf(renderer)).not.toContain('0 min');
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
  expect(copy).not.toContain('Duration ·');
  expect(copy).not.toContain('hr');
});

test('conversation list names Flutter ConversationListItem padded GET completed instead of remapping to Duration unavailable', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:padded-completed',
    title: 'Market street',
    summary: 'A walk.',
    searchableText: 'Market street\nA walk.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: '  completed  ',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  const page = {
    ...incompletePage,
    windowStatus: 'complete' as const,
    complete: true,
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  let padded!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    padded = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{status: 'success', value: {items: [item], page}}}
      />,
    );
  });
  expect(textOf(padded)).toContain('Market street');
  expect(textOf(padded)).not.toContain('Duration unavailable');
  act(() => {
    padded.update(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [{...item, status: 'completed '}],
            page,
          },
        }}
      />,
    );
  });
  expect(textOf(padded)).not.toContain('Duration unavailable');
  act(() => {
    padded.update(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [{...item, status: 'completed\u0085'}],
            page,
          },
        }}
      />,
    );
  });
  expect(textOf(padded)).not.toContain('Duration unavailable');
  act(() => {
    padded.update(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [{...item, status: 'completed'}],
            page,
          },
        }}
      />,
    );
  });
  expect(textOf(padded)).toContain('Duration unavailable');
});

test('conversation list and detail omit Flutter ConversationListItem unused capturedAt', () => {
  const older = new Date(2025, 7, 10, 12, 0);
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
  expect(copy).toContain('Device capture');
  expect(copy).not.toContain('Captured (device time)');
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
  expect(copy).not.toContain('Status ·');
  expect(copy).not.toContain(conversationStatusCopy('in_progress'));
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
  expect(copy).not.toContain('Status ·');
  expect(copy).not.toContain('Status unavailable');
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

test('conversation list omits Flutter ConversationListItem unused capturedAt', () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
  const captured = new Date(2025, 7, 10, 12, 0);
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
    expect(copy).toContain('Device capture');
    expect(copy).toContain('Untimed recording');
    expect(copy).not.toContain('Captured (device time)');
    expect(copy).not.toContain('1970');
  } finally {
    dimensions.mockRestore();
  }
});

test('conversation list keeps GET locked flags and omits Flutter ConversationListItem Discarded chip', () => {
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
  expect(copy).not.toContain('Discarded');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Locked conversation',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Discarded conversation',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(node => node.props.children === 'Discarded'),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Not locked',
    ),
  ).toHaveLength(0);
});

test('discarded list rows name GET transcript span instead of Duration unavailable', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:discarded-timed',
    title: 'Speaker 1: Hello from the recording',
    summary: 'Saved words',
    searchableText: 'Speaker 1: Hello from the recording\nSaved words',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: true,
    transcriptEndSeconds: 120,
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
  expect(copy).toContain('2m');
  expect(copy).not.toContain('Duration unavailable');
});

test('non-discarded list rows name GET transcript span instead of Duration unavailable', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:timed',
    title: 'Product review',
    summary: 'Talked through the release.',
    searchableText: 'Product review\nTalked through the release.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
    transcriptEndSeconds: 120,
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
  expect(copy).toContain('2m');
  expect(copy).not.toContain('Duration unavailable');
});

test('processing list rows name GET transcript span without a finish clock', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:processing-timed',
    title: 'Product review',
    summary: 'Talked through the release.',
    searchableText: 'Product review\nTalked through the release.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'processing',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
    transcriptEndSeconds: 120,
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
  expect(copy).toContain('2m');
  expect(copy).not.toContain('Duration unavailable');
});

test('conversation list names Flutter empty GET titles without Failed chips', () => {
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
  expect(copy).not.toContain('Conversation title unavailable');
  expect(copy).not.toContain('Failed');
  expect(copy).toContain('Hello');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Failed conversation',
    ),
  ).toHaveLength(0);
  expect(copy).not.toContain(conversationStatusCopy('in_progress'));
});

test('conversation list names Flutter ConversationListItem empty GET title whitespace', () => {
  const base = {
    kind: 'conversation' as const,
    title: ' \t\n',
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
                id: 'recording:whitespace-title',
                status: 'completed',
              },
              {
                ...base,
                id: 'recording:padded-title',
                title: '  Morning walk  ',
                searchableText: '  Morning walk  ',
                status: 'completed',
              },
              {
                ...base,
                id: 'recording:next-line-title',
                title: '\u0085',
                searchableText: '\u0085',
                status: 'completed',
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
  const titles = renderer.root.findAll(
    node =>
      node.type === Text &&
      (node.props.children === ' \t\n' ||
        node.props.children === '  Morning walk  ' ||
        node.props.children === '\u0085'),
  );
  expect(titles.length).toBeGreaterThan(2);
  expect(textOf(renderer)).toContain(' \t\n');
  expect(textOf(renderer)).toContain('  Morning walk  ');
  expect(textOf(renderer)).toContain('\u0085');
  expect(textOf(renderer)).not.toContain('Conversation title unavailable');
});

test('conversation list names Flutter ConversationListItem empty GET ids without hiding neighbors', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Empty id',
    summary: '',
    searchableText: 'Empty id',
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
    status: 'completed' as const,
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
                id: 'kept',
                title: 'Kept title',
                searchableText: 'Kept title',
              },
              {
                ...base,
                id: '',
              },
              {
                ...base,
                id: ' \t',
                title: 'Whitespace id',
                searchableText: 'Whitespace id',
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
  expect(copy).toContain('Kept title');
  expect(copy).toContain('Empty id');
  expect(copy).toContain('Whitespace id');
  expect(copy).not.toContain('Conversations could not be loaded.');
  expect(copy).not.toContain(conversationsEmptyCopy());
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Open conversation Empty id',
    ),
  ).toBeDefined();
});

test('conversation list omits Flutter ConversationListItem Processing chips', () => {
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
    ),
  ).toHaveLength(0);
  expect(copy).not.toContain('Processing');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Merging... conversation',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Merging... conversation' &&
        node.props.children === 'Merging...',
    ).length,
  ).toBeGreaterThan(0);
  expect(copy).toContain('Merging...');
  expect(copy).not.toContain(conversationStatusCopy('in_progress'));
});

test('conversation list omits Flutter MergingIndicator when GET status is padded', () => {
  const base = {
    kind: 'conversation' as const,
    title: 'Standup recap',
    summary: 'Notes',
    searchableText: 'Standup recap\nNotes',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
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
                id: 'recording:padded-merging',
                status: '  merging  ',
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
  expect(copy).toContain('Standup recap');
  expect(copy).not.toContain('Merging...');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Merging... conversation',
    ),
  ).toHaveLength(0);
});

test('conversation list omits Flutter ConversationListItem unused overview', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-overview-one',
    title: 'Morning standup',
    summary: 'Notes from the standup',
    searchableText: 'Morning standup\nNotes from the standup',
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
  expect(copy).toContain('Morning standup');
  expect(copy).not.toContain('Notes from the standup');
  expect(copy).not.toContain('Conversation summary is not ready yet.');
  expect(copy).not.toContain('Conversation summary unavailable');
});

test('conversation list names GET emoji including Flutter ConversationListItem empty GET emoji', () => {
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
      node =>
        node.props.accessibilityLabel === 'Conversation emoji' &&
        node.props.children === '🚀',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Conversation emoji' &&
        node.props.children === ' \u0085 ',
    ).length,
  ).toBeGreaterThan(0);
  expect(textOf(renderer)).not.toContain('🧠');
  expect(textOf(renderer)).toContain('\u0085');
});

test('conversation list names Flutter omitted GET emoji 🧠 when not discarded', () => {
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
    emoji: conversationStructuredEmojiDefaultCopy(),
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        loading={false}
        outcome={{
          status: 'success',
          value: {
            items: [{...base, id: 'omi-default-emoji'}],
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
  expect(textOf(renderer)).toContain(conversationStructuredEmojiDefaultCopy());
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Conversation emoji' &&
        node.props.children === conversationStructuredEmojiDefaultCopy(),
    ).length,
  ).toBeGreaterThan(0);
});

test('conversation list names Flutter New chrome for a just-created row', () => {
  const now = Date.now();
  const base = {
    kind: 'conversation' as const,
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    updatedAt: new Date(now - 20_000).toISOString(),
    startedAt: new Date(now - 50_000).toISOString(),
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
                createdAt: new Date(now - 50_000).toISOString(),
                finishedAt: new Date(now - 20_000).toISOString(),
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
  expect(textOf(renderer)).not.toContain('30s');
  expect(textOf(renderer)).toContain('Older talk');
  expect(textOf(renderer)).toContain('1m');
});

test('conversation list names GET category including Flutter ConversationListItem empty GET tags', () => {
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
                id: 'omi-other',
                title: 'No category',
                category: 'other',
              },
              {
                ...base,
                id: 'omi-empty',
                title: 'Whitespace category',
                category: ' \u0085 ',
              },
              {
                ...base,
                id: 'omi-whitespace-pipe',
                title: 'Pipe talk',
                source: 'screenpipe',
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
  expect(
    renderer.root.findAll(
      node => node.type === 'Text' && node.props.children === 'Discarded',
    ).length,
  ).toBeGreaterThan(0);
  expect(textOf(renderer)).toContain('Other');
  expect(textOf(renderer)).toContain('Screenpipe');
  expect(textOf(renderer)).not.toContain('work');
  expect(textOf(renderer)).not.toContain('other');
  const emptyRow = renderer.root.find(
    node =>
      node.props.accessibilityLabel === 'Open conversation Whitespace category',
  );
  expect(
    emptyRow.findAll(
      node => node.type === 'Text' && node.props.children === ' \u0085 ',
    ).length,
  ).toBeGreaterThan(0);
  expect(textOf(renderer)).toContain('\u0085');
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
                category: 'work',
              },
              {
                ...base,
                id: 'omi-sdcard',
                title: 'Card talk',
                source: 'sdcard',
                discarded: true,
                category: 'work',
              },
              {
                ...base,
                id: 'omi-rayban',
                title: 'Ray talk',
                source: 'rayban_meta',
                category: 'work',
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

test('conversation list names Flutter getTag category when GET source is padded', () => {
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
                id: 'omi-padded-screenpipe',
                source: '  screenpipe  ',
                category: 'work',
              },
              {
                ...base,
                id: 'omi-padded-discarded-screenpipe',
                title: 'Discarded pipe',
                source: '  screenpipe  ',
                discarded: true,
                category: 'work',
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
  expect(copy).toContain('Work');
  expect(copy).toContain('Discarded');
  expect(copy).not.toContain('Screenpipe');
});

test('conversation list names Flutter ConversationListItem empty GET category tags', () => {
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
                id: 'omi-empty-screenpipe',
                title: 'Empty category talk',
                source: 'screenpipe',
              },
              {
                ...base,
                id: 'omi-whitespace-glass',
                title: 'Whitespace category talk',
                source: 'openglass',
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
  const copy = textOf(renderer);
  expect(copy).toContain('Empty category talk');
  expect(copy).toContain('Whitespace category talk');
  expect(copy).not.toContain('Screenpipe');
  expect(copy).toContain('OmiGlass');
});

test('compact conversation list omits Flutter ConversationListItem mobile tags', () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
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
    expect(copy).toContain('Glass talk');
    expect(copy).not.toContain('Screenpipe');
    expect(copy).not.toContain('OmiGlass');
    expect(copy).not.toContain('Work');
  } finally {
    dimensions.mockRestore();
  }
});

test('compact conversation list omits Flutter ConversationListItem mobile photos', () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
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
    const copy = textOf(renderer);
    expect(copy).toContain('Morning standup');
    expect(copy).not.toContain('2 photos');
    expect(copy).not.toContain('3 photos');
  } finally {
    dimensions.mockRestore();
  }
});

test('compact conversation list omits Flutter ConversationListItem mobile Discarded chip', () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 390,
    height: 844,
    scale: 1,
    fontScale: 1,
  });
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
                  kind: 'conversation',
                  id: 'omi-discarded-chip',
                  title: 'Product review',
                  summary: 'Notes',
                  searchableText: 'Product review\nNotes',
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
                  discarded: true,
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
    expect(textOf(renderer)).toContain('Product review');
    expect(textOf(renderer)).not.toContain('Discarded');
    expect(
      renderer.root.findAll(
        node => node.props.accessibilityLabel === 'Discarded conversation',
      ),
    ).toHaveLength(0);
    expect(
      renderer.root.findAll(node => node.props.children === 'Discarded'),
    ).toHaveLength(0);
  } finally {
    dimensions.mockRestore();
  }
});

test('conversation list names Flutter ConversationListItem discarded photos only', () => {
  const native = require('react-native') as typeof import('react-native');
  const dimensions = jest.spyOn(native, 'useWindowDimensions').mockReturnValue({
    width: 1024,
    height: 768,
    scale: 1,
    fontScale: 1,
  });
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
  } finally {
    dimensions.mockRestore();
  }
});

test('conversation list names discarded GET transcript excerpt as the title', () => {
  const excerpt =
    '[00:00:00 - 00:00:02] Speaker 1: Hello from the recording';
  const base = {
    kind: 'conversation' as const,
    summary: 'Notes',
    searchableText: `${excerpt}\nNotes`,
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
                id: 'omi-discarded-speech',
                title: excerpt,
                discarded: true,
              },
              {
                ...base,
                id: 'omi-kept-speech',
                title: 'Real title',
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
  expect(copy).toContain(excerpt);
  expect(copy).toContain('Real title');
  expect(copy).not.toContain('Discarded');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Discarded conversation',
    ),
  ).toHaveLength(0);
});

test('conversation list names discarded empty GET transcript instead of structured title', () => {
  const base = {
    kind: 'conversation' as const,
    searchableText: '\nActual overview',
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
                id: 'omi-discarded-empty',
                title: '',
                summary: 'Actual overview',
                discarded: true,
              },
              {
                ...base,
                id: 'omi-kept-titled',
                title: 'Kept title',
                summary: 'Actual overview',
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
  expect(copy).toContain('Kept title');
  expect(copy).not.toContain('Actual overview');
  expect(copy).not.toContain('Discarded');
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
          {id: 'goal-missing', title: 'Missing metrics', target_value: 10},
          {id: 'goal-empty', title: ' \t', current_value: 1, target_value: 2},
          {id: ' \t', title: 'Whitespace id', current_value: 2, target_value: 2},
          {id: '\u0085', title: 'Next line id', current_value: 2.5, target_value: 2.5},
          {id: '  padded  ', title: 'Padded id', current_value: 1, target_value: 1},
          {id: '', title: 'Empty id', current_value: 5, target_value: 8},
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
  expect(tree).toContain('Missing metrics');
  expect(tree).toContain('0/10');
  expect(tree).toContain('1/2');
  expect(tree).toContain('Whitespace id');
  expect(tree).toContain('Next line id');
  expect(tree).toContain('Padded id');
  expect(tree).toContain('Empty id');
  expect(tree).toContain(conversationsEmptyCopy());
  expect(tree).not.toContain('No conversations yet.');
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

test('conversation list names Flutter Goal.fromJson padded GET current_value instead of remapping to a progress chip', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'goal-padded',
            title: 'Padded metrics',
            current_value: '  3  ',
            target_value: 10,
          },
          {
            id: 'goal-read',
            title: 'Read 20 books',
            current_value: '3',
            target_value: '10',
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
  expect(tree).not.toContain('Padded metrics');
  expect(tree).not.toContain('goal-padded');
  expect(tree).not.toContain('No goals');
  expect(tree).not.toContain('Add');
  act(() => renderer.unmount());
});

test('conversation list names Flutter Goal.fromGenerated type-wrong GET advice instead of remapping to a progress chip', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'goal-wrong',
            title: 'Type-wrong extras',
            current_value: 3,
            target_value: 10,
            advice: 1,
          },
          {
            id: 'goal-read',
            title: 'Read 20 books',
            current_value: 3,
            target_value: 10,
            success_criteria: ['done'],
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
  expect(tree).not.toContain('Type-wrong extras');
  expect(tree).not.toContain('goal-wrong');
  expect(tree).not.toContain('No goals');
  expect(tree).not.toContain('Add');
  act(() => renderer.unmount());
});

test('conversation list names a failed GET goals instead of empty success', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
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
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).toContain(conversationsEmptyCopy());
  expect(tree).not.toContain('No conversations yet.');
  expect(tree).not.toContain('No goals');
  expect(tree).not.toContain('🎯');
  expect(tree).not.toContain('Add');
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
          {id: ' \t', name: 'Whitespace id'},
          {id: '', name: 'Blank id'},
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
  expect(tree).toContain('Whitespace id');
  expect(tree).toContain('Blank id');
  expect(tree).not.toContain('folder-work');
  expect(tree).not.toContain('folder-empty');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Show  \t conversations',
    ),
  ).toBeDefined();
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

test('conversation list names GET folder color on the selected chip', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'folder-work',
            name: 'Work',
            color: '#3B82F6',
            icon: '💼',
            conversation_count: 99,
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
            items: [
              {
                kind: 'conversation',
                id: 'chat:work',
                title: 'Work standup',
                summary: 'Notes',
                searchableText: 'Work standup\nNotes',
                createdAt: '2026-09-07T00:00:00.000Z',
                updatedAt: '2026-09-07T00:01:00.000Z',
                startedAt: '2026-09-07T00:00:00.000Z',
                finishedAt: null,
                starred: false,
                status: 'in_progress',
                source: 'chat',
                visibility: 'private',
                locked: false,
                discarded: false,
                folderId: 'folder-work',
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
  expect(tree).not.toContain('#3B82F6');
  expect(tree).toContain('💼');
  expect(tree).not.toContain('99');
  expect(tree).not.toContain('Add');
  const chip = renderer.root.find(
    node => node.props.accessibilityLabel === 'Show Work conversations',
  );
  const idle = Object.assign(
    {},
    ...(typeof chip.props.style === 'function'
      ? chip.props.style({pressed: false})
      : [chip.props.style]
    )
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(idle.backgroundColor).not.toBe('rgba(59, 130, 246, 0.15)');
  await act(async () => {
    chip.props.onPress();
  });
  const selectedChip = renderer.root.find(
    node => node.props.accessibilityLabel === 'Show Work conversations',
  );
  const selected = Object.assign(
    {},
    ...(typeof selectedChip.props.style === 'function'
      ? selectedChip.props.style({pressed: false})
      : [selectedChip.props.style]
    )
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(selected.backgroundColor).toBe('rgba(59, 130, 246, 0.15)');
  expect(selected.borderColor).toBe('#3B82F6');
  const label = Object.assign(
    {},
    ...[selectedChip.findAllByType(Text)[0]?.props.style]
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(label.color).toBe('#3B82F6');
  expect(textOf(renderer)).not.toContain('#3B82F6');
});

test('conversation list names GET omitted folder color as Flutter #6B7280 on the selected chip', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([{id: 'folder-work', name: 'Work'}]),
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
                id: 'chat:work',
                title: 'Work standup',
                summary: 'Notes',
                searchableText: 'Work standup\nNotes',
                createdAt: '2026-09-07T00:00:00.000Z',
                updatedAt: '2026-09-07T00:01:00.000Z',
                startedAt: '2026-09-07T00:00:00.000Z',
                finishedAt: null,
                starred: false,
                status: 'in_progress',
                source: 'chat',
                visibility: 'private',
                locked: false,
                discarded: false,
                folderId: 'folder-work',
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
  expect(textOf(renderer)).toContain('Work');
  expect(textOf(renderer)).not.toContain('#6B7280');
  const chip = renderer.root.find(
    node => node.props.accessibilityLabel === 'Show Work conversations',
  );
  await act(async () => {
    chip.props.onPress();
  });
  const selectedChip = renderer.root.find(
    node => node.props.accessibilityLabel === 'Show Work conversations',
  );
  const selected = Object.assign(
    {},
    ...(typeof selectedChip.props.style === 'function'
      ? selectedChip.props.style({pressed: false})
      : [selectedChip.props.style]
    )
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(selected.backgroundColor).toBe('rgba(107, 114, 128, 0.15)');
  expect(selected.borderColor).toBe('#6B7280');
  const label = Object.assign(
    {},
    ...[selectedChip.findAllByType(Text)[0]?.props.style]
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(label.color).toBe('#6B7280');
  expect(textOf(renderer)).not.toContain('#6B7280');
});

test('conversation list names Flutter FolderTabs padded GET color as gray on the selected chip', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'folder-work',
            name: 'Work',
            color: '  #3b82f6  ',
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
            items: [
              {
                kind: 'conversation',
                id: 'chat:work',
                title: 'Work standup',
                summary: 'Notes',
                searchableText: 'Work standup\nNotes',
                createdAt: '2026-09-07T00:00:00.000Z',
                updatedAt: '2026-09-07T00:01:00.000Z',
                startedAt: '2026-09-07T00:00:00.000Z',
                finishedAt: null,
                starred: false,
                status: 'in_progress',
                source: 'chat',
                visibility: 'private',
                locked: false,
                discarded: false,
                folderId: 'folder-work',
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
  expect(textOf(renderer)).toContain('Work');
  expect(textOf(renderer)).not.toContain('#3B82F6');
  expect(textOf(renderer)).not.toContain('#6B7280');
  const chip = renderer.root.find(
    node => node.props.accessibilityLabel === 'Show Work conversations',
  );
  await act(async () => {
    chip.props.onPress();
  });
  const selectedChip = renderer.root.find(
    node => node.props.accessibilityLabel === 'Show Work conversations',
  );
  const selected = Object.assign(
    {},
    ...(typeof selectedChip.props.style === 'function'
      ? selectedChip.props.style({pressed: false})
      : [selectedChip.props.style]
    )
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(selected.backgroundColor).toBe('rgba(107, 114, 128, 0.15)');
  expect(selected.backgroundColor).not.toBe('rgba(59, 130, 246, 0.15)');
  expect(selected.borderColor).toBe('#6B7280');
  const label = Object.assign(
    {},
    ...[selectedChip.findAllByType(Text)[0]?.props.style]
      .flat(Infinity)
      .filter(entry => entry && typeof entry === 'object'),
  );
  expect(label.color).toBe('#6B7280');
  expect(textOf(renderer)).not.toContain('#3B82F6');
  expect(textOf(renderer)).not.toContain('#6B7280');
});

test('conversation list names Flutter FolderTabs padded GET icon as default folder', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'folder-exact',
            name: 'Exact',
            icon: '💼',
          },
          {
            id: 'folder-padded',
            name: 'Padded',
            icon: '  💼  ',
          },
          {
            id: 'folder-trailing',
            name: 'Trailing',
            icon: '💼 ',
          },
          {
            id: 'folder-next-line',
            name: 'Next line',
            icon: '\u0085💼',
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
            items: [
              {
                kind: 'conversation',
                id: 'chat:work',
                title: 'Work standup',
                summary: 'Notes',
                searchableText: 'Work standup\nNotes',
                createdAt: '2026-09-07T00:00:00.000Z',
                updatedAt: '2026-09-07T00:01:00.000Z',
                startedAt: '2026-09-07T00:00:00.000Z',
                finishedAt: null,
                starred: false,
                status: 'in_progress',
                source: 'chat',
                visibility: 'private',
                locked: false,
                discarded: false,
                folderId: 'folder-exact',
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
  expect(tree).toContain('Exact');
  expect(tree).toContain('Padded');
  expect(tree).toContain('Trailing');
  expect(tree).toContain('Next line');
  expect(tree).toContain('💼');
  const chipCopy = (label: string) =>
    renderer.root
      .find(node => node.props.accessibilityLabel === label)
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
  expect(chipCopy('Show Exact conversations')).toContain('💼');
  expect(chipCopy('Show Padded conversations')).not.toContain('💼');
  expect(chipCopy('Show Trailing conversations')).not.toContain('💼');
  expect(chipCopy('Show Next line conversations')).not.toContain('💼');
});

test('conversation list names a failed GET folders instead of empty success', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
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
  expect(tree).toContain('Folders');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).toContain('Work standup');
  expect(tree).toContain('Inbox chat');
  expect(tree).not.toContain('Add');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Show Work conversations',
    ),
  ).toHaveLength(0);
  expect(
    request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'PATCH',
    ),
  ).toBe(false);
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
          {
            event_id: ' \t',
            title: 'Whitespace id',
            start_time: '2026-09-07T18:00:00.000Z',
            end_time: '2026-09-07T19:00:00.000Z',
          },
          {
            event_id: '',
            title: 'Blank id',
            start_time: '2026-09-07T19:00:00.000Z',
            end_time: '2026-09-07T20:00:00.000Z',
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
  expect(tree).toContain('Not captured (4)');
  expect(tree).toContain('Design review');
  expect(tree).toContain('Whitespace id');
  expect(tree).toContain('Blank id');
  expect(tree).toContain(
    captureGapTimeRangeCopy(
      Date.parse('2026-09-07T15:00:00.000Z'),
      Date.parse('2026-09-07T16:30:00.000Z'),
    ),
  );
  expect(tree).toContain(
    captureGapTimeRangeCopy(
      Date.parse('2026-09-07T17:00:00.000Z'),
      Date.parse('2026-09-07T18:00:00.000Z'),
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
  expect(textOf(renderer)).not.toContain('Not captured (4)');
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

test('conversation list names a failed GET calendar capture gaps instead of empty success', async () => {
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
  const request = jest.fn(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/calendar/capture-gaps?')
    ) {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
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
  expect(tree).toContain('Not captured');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).toContain('Work chat');
  expect(tree).not.toContain('Design review');
  expect(tree).not.toContain('html_link');
  expect(tree).not.toContain('Add');
  expect(
    request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'PATCH',
    ),
  ).toBe(false);
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
  expect(textOf(renderer)).toContain(conversationsEmptyCopy());
  expect(textOf(renderer)).not.toContain('No conversations yet.');
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

test('conversation list names Flutter FolderProvider fromJson padded GET created_at instead of empty folder chips', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'folder-work',
            name: 'Neighbor',
            created_at: '  2026-09-07T00:00:00.000Z  ',
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
            items: [
              {
                kind: 'conversation',
                id: 'chat:work',
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
                locked: false,
                discarded: false,
                folderId: 'folder-work',
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
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi folders are malformed')),
  );
  expect(tree).toContain('Folders');
  expect(tree).toContain('Standup');
  expect(tree).not.toContain('Neighbor');
});

test('conversation list names Flutter Folder.fromGenerated type-wrong GET created_at instead of empty folder chips', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'folder-work',
            name: 'Neighbor',
            created_at: 1,
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
            items: [
              {
                kind: 'conversation',
                id: 'chat:work',
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
                locked: false,
                discarded: false,
                folderId: 'folder-work',
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
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi folders are malformed')),
  );
  expect(tree).toContain('Folders');
  expect(tree).toContain('Standup');
  expect(tree).not.toContain('Neighbor');
});

test('conversation list names Flutter Folder.fromGenerated type-wrong GET description instead of empty folder chips', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'folder-work',
            name: 'Neighbor',
            description: 1,
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
            items: [
              {
                kind: 'conversation',
                id: 'chat:work',
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
                locked: false,
                discarded: false,
                folderId: 'folder-work',
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
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi folders are malformed')),
  );
  expect(tree).toContain('Folders');
  expect(tree).toContain('Standup');
  expect(tree).not.toContain('Neighbor');
});

test('conversation list names Flutter Folder.fromGenerated type-wrong GET color instead of empty folder chips', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/folders') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'folder-work',
            name: 'Neighbor',
            color: 1,
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
            items: [
              {
                kind: 'conversation',
                id: 'chat:work',
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
                locked: false,
                discarded: false,
                folderId: 'folder-work',
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
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi folders are malformed')),
  );
  expect(tree).toContain('Folders');
  expect(tree).toContain('Standup');
  expect(tree).not.toContain('Neighbor');
});

