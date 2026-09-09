import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import type {
  ConversationProjection,
  MemoryProjection,
} from '../desktopReadClient';
import {ConversationRow, ReadRow} from './DesktopRows';

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

test('a zero Home current timestamp says Time unavailable instead of omitting the clock', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-epoch',
    title: 'Undated memory',
    summary: 'Body',
    searchableText: 'Undated memory\nBody',
    citations: [],
    timestamp: 0,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Time unavailable');
  expect(copy).toContain('Undated memory');
  expect(copy).not.toContain('1970');
});

test('Home currents keep listen overview speech on the row title', () => {
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
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  expect(textOf(renderer)).toContain(summary);
  expect(
    renderer.root.findAll(
      node => node.props.numberOfLines === 3 && node.props.children === summary,
    ).length,
  ).toBeGreaterThan(0);
});

test('Home currents keep chat last-turn overview off the timestamp meta', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:session-alpha',
    title: 'Hi',
    summary:
      'Later independent turn with more speech than a timestamp line keeps',
    searchableText:
      'Hi\nLater independent turn with more speech than a timestamp line keeps',
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
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  expect(textOf(renderer)).toContain('Hi');
  expect(textOf(renderer)).toContain(item.summary);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 2 && node.props.children === item.summary,
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes(item.summary),
    ).length,
  ).toBe(0);
});

test('Library rows keep chat last-turn overview off the timestamp meta', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:session-alpha',
    title: 'Hi',
    summary:
      'Later independent turn with more speech than a timestamp line keeps',
    searchableText:
      'Hi\nLater independent turn with more speech than a timestamp line keeps',
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
    renderer = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 2 && node.props.children === item.summary,
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes(item.summary),
    ).length,
  ).toBe(0);
});
