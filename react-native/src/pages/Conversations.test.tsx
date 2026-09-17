import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {ScrollView, Text, useWindowDimensions} from 'react-native';
import {ConversationsPage} from './Conversations';
import type {
  ConversationProjection,
  DesktopReadProjection,
  DomainReadOutcome,
} from '../desktopReadClient';
import {OmiAvatar} from '../ui/OmiAvatar';
import {FocusPressable} from '../ui/Pressable';

jest.mock('../app/useReduceMotion', () => ({useReduceMotion: () => true}));
jest.mock('react-native/Libraries/Utilities/useWindowDimensions', () => ({
  __esModule: true,
  default: jest.fn(),
}));

beforeEach(() => {
  (useWindowDimensions as jest.Mock).mockReturnValue({
    width: 390,
    height: 820,
    scale: 2,
    fontScale: 1,
  });
});

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
  act(() => renderer.unmount());
});

const items: ConversationProjection[] = [
  {id: 'starred', title: 'Quiet workspace', starred: true},
  {id: 'other', title: 'Shared workspace', starred: false},
  {id: 'walk', title: 'Afternoon walk', starred: true},
].map(item => ({
  ...item,
  kind: 'conversation',
  summary: 'Saved notes',
  searchableText: '',
  createdAt: '2026-09-17T10:00:00Z',
  updatedAt: null,
  startedAt: null,
  finishedAt: null,
  status: 'completed',
  source: 'desktop',
  visibility: 'private',
  folderId: null,
  locked: false,
  discarded: false,
}));
const outcome: DomainReadOutcome<DesktopReadProjection> = {
  status: 'success',
  value: {
    items,
    page: {
      windowStatus: 'complete',
      complete: true,
      hasMore: false,
      nextCursor: null,
      completenessStatus: 'complete',
      reasons: [],
    },
  },
};

test('mobile search and star filters compose; clearing search preserves stars, resetting clears both', () => {
  let tree!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    tree = ReactTestRenderer.create(
      <ConversationsPage embedded outcome={outcome} loading={false} />,
    );
  });
  const control = (label: string) =>
    tree.root.findAllByProps({accessibilityLabel: label})[0];
  const rows = () =>
    tree.root
      .findAllByType(FocusPressable)
      .filter(node =>
        node.props.accessibilityLabel?.startsWith('Open conversation '),
      )
      .map(node => node.props.accessibilityLabel);
  act(() =>
    control('Search loaded conversations').props.onChangeText(' workspace '),
  );
  act(() => control('Show starred conversations').props.onPress());
  act(() => control('Show starred conversations').props.onPress());
  expect(rows()).toEqual(['Open conversation Quiet workspace']);
  act(() => control('Show all conversations').props.onPress());
  expect(rows()).toEqual([
    'Open conversation Quiet workspace',
    'Open conversation Shared workspace',
  ]);
  act(() => control('Show starred conversations').props.onPress());
  act(() => control('Clear conversation search').props.onPress());
  expect(rows()).toEqual([
    'Open conversation Quiet workspace',
    'Open conversation Afternoon walk',
  ]);
  expect(
    control('Show starred conversations').props.accessibilityState.selected,
  ).toBe(true);
  act(() =>
    control('Search loaded conversations').props.onChangeText('not found'),
  );
  expect(rows()).toEqual([]);
  act(() => control('Clear conversation filters').props.onPress());
  expect(control('Search loaded conversations').props.value).toBe('');
  expect(
    control('Show all conversations').props.accessibilityState.selected,
  ).toBe(true);
  expect(rows()).toHaveLength(3);
  act(() => tree.unmount());
});

test('mobile detail Back stays outside the transcript and restores active search', () => {
  let tree!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    tree = ReactTestRenderer.create(
      <ConversationsPage embedded outcome={outcome} loading={false} />,
    );
  });
  const control = (label: string) =>
    tree.root.findAllByProps({accessibilityLabel: label})[0];
  act(() =>
    control('Search loaded conversations').props.onChangeText('workspace'),
  );
  act(() => control('Open conversation Quiet workspace').props.onPress());
  expect(
    tree.root
      .findByType(ScrollView)
      .findAllByProps({accessibilityLabel: 'Back to conversations'}),
  ).toHaveLength(0);
  expect(textOf(tree)).toContain('Saved notes');
  act(() => control('Back to conversations').props.onPress());
  expect(control('Search loaded conversations').props.value).toBe('workspace');
  expect(control('Open conversation Shared workspace')).toBeDefined();
  act(() => tree.unmount());
});

test('loading uses the reduced-motion mark without claiming an empty library; retry stays available after failure', () => {
  const refresh = jest.fn();
  let tree!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    tree = ReactTestRenderer.create(
      <ConversationsPage embedded outcome={null} loading onRefresh={refresh} />,
    );
  });
  expect(textOf(tree)).toContain('Loading conversations…');
  expect(textOf(tree)).not.toContain('No conversations yet.');
  expect(tree.root.findByType(OmiAvatar).props.reduceMotion).toBe(true);
  expect(
    tree.root.findAllByProps({accessibilityLabel: 'Refresh conversations'})[0]
      .props.disabled,
  ).toBe(true);
  act(() =>
    tree.update(
      <ConversationsPage
        embedded
        outcome={{status: 'error', error: 'Connection interrupted'}}
        loading={false}
        onRefresh={refresh}
      />,
    ),
  );
  const retry = tree.root.findAllByProps({
    accessibilityLabel: 'Refresh conversations',
  })[0];
  expect(retry.props.disabled).toBe(false);
  expect(textOf(tree)).toContain('Connection interrupted');
  expect(textOf(tree)).not.toContain('No conversations yet.');
  act(() => retry.props.onPress());
  expect(refresh).toHaveBeenCalledTimes(1);
  act(() => tree.unmount());
});

test('the shared bottom search owns the query without a second page input', () => {
  const onChange = jest.fn();
  let tree!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    tree = ReactTestRenderer.create(
      <ConversationsPage
        embedded
        outcome={outcome}
        loading={false}
        search={{value: 'workspace', onChange}}
      />,
    );
  });
  expect(
    tree.root.findAllByProps({
      accessibilityLabel: 'Search loaded conversations',
    }),
  ).toHaveLength(0);
  expect(textOf(tree)).toContain('Quiet workspace');
  expect(textOf(tree)).not.toContain('Afternoon walk');
  act(() =>
    tree.update(
      <ConversationsPage
        embedded
        outcome={outcome}
        loading={false}
        search={{value: 'unmatched', onChange}}
      />,
    ),
  );
  act(() =>
    tree.root
      .findAllByProps({accessibilityLabel: 'Clear conversation filters'})[0]
      .props.onPress(),
  );
  expect(onChange).toHaveBeenCalledWith('');
  expect(textOf(tree)).not.toContain('Quiet workspace');
  act(() => tree.unmount());
});
