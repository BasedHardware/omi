import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {ConversationsPage} from './Conversations';
import {
  clockLabel,
  desktopBackendUnavailableCopy,
  type ConversationProjection,
} from '../desktopReadClient';

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
