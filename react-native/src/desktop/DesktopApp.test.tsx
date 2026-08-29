import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text, TextInput} from 'react-native';
import {DesktopApp} from './DesktopApp';

jest.mock('../ui/GlassPanel', () => {
  const ReactModule = require('react');
  const {View} = require('react-native');
  return {
    GlassPanel: (props: Record<string, unknown>) =>
      ReactModule.createElement(View, props),
  };
});

const outcomes = {
  conversations: {
    status: 'success' as const,
    value: {
      items: [
        {
          kind: 'conversation' as const,
          id: 'conversation-1',
          title: 'Product review',
          summary: 'Reviewed the current desktop direction.',
          searchableText: 'product review current desktop direction',
          createdAt: '2026-08-30T10:00:00.000Z',
          updatedAt: '2026-08-30T10:10:00.000Z',
          startedAt: '2026-08-30T10:00:00.000Z',
          finishedAt: '2026-08-30T10:10:00.000Z',
          starred: false,
          status: 'completed',
          source: 'desktop',
          visibility: 'private' as const,
          folderId: null,
          locked: false,
          discarded: false,
        },
      ],
      page: {
        windowStatus: 'complete' as const,
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete' as const,
        reasons: [],
      },
    },
  },
  memories: {
    status: 'success' as const,
    value: {
      items: [],
      page: {
        windowStatus: 'complete' as const,
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete' as const,
        reasons: [],
      },
    },
  },
  tasks: {
    status: 'success' as const,
    value: {
      items: [],
      page: {
        windowStatus: 'complete' as const,
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete' as const,
        reasons: [],
      },
    },
  },
};

function renderedText(renderer: ReactTestRenderer.ReactTestRenderer): string {
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

test('renders the shipping search-first desktop hierarchy', () => {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <DesktopApp
        onOpenChat={jest.fn()}
        onRefresh={jest.fn()}
        outcomes={outcomes}
        reads={outcomes.conversations.value.items}
        readsPhase="ready"
      />,
    );
  });
  const tree = renderedText(renderer!);
  expect(
    renderer!.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain("Search what you've seen and heard…");
  expect(tree).toContain('Brain Map');
  expect(tree).toContain('Product review');
  expect(tree).toContain('Library');
  expect(tree).toContain('Rewind');
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Omi disconnected');
  expect(tree).not.toContain('Devices');
});

test('keeps an unavailable read as an inline timeline state', () => {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <DesktopApp
        onOpenChat={jest.fn()}
        onRefresh={jest.fn()}
        outcomes={null}
        reads={[]}
        readsPhase="unavailable"
      />,
    );
  });
  const tree = renderedText(renderer!);
  expect(tree).toContain('Offline · showing what is available on this Mac');
  expect(
    renderer!.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain("Search what you've seen and heard…");
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Sign in to Omi cloud');
});
