import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {ConversationsPage} from './Conversations';
import type {ConversationProjection} from '../desktopReadClient';

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
    searchableText: 'Processing conversation…\n',
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
  expect(textOf(renderer)).not.toContain('No conversations yet.');
});
