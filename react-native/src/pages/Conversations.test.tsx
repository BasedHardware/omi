import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {
  AppState,
  type AppStateStatus,
  ScrollView,
  Text,
  useWindowDimensions,
} from 'react-native';
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
  jest.useFakeTimers();
  AppState.currentState = 'active';
  (useWindowDimensions as jest.Mock).mockReturnValue({
    width: 390,
    height: 820,
    scale: 2,
    fontScale: 1,
  });
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
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

test('loading keeps the reduced-motion mark and failures retry automatically without a refresh button', () => {
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
    tree.root.findAllByProps({accessibilityLabel: 'Refresh conversations'}),
  ).toHaveLength(0);
  act(() => jest.advanceTimersByTime(15000));
  expect(refresh).not.toHaveBeenCalled();
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
  expect(textOf(tree)).toContain('Connection interrupted');
  expect(textOf(tree)).not.toContain('No conversations yet.');
  act(() => jest.advanceTimersByTime(15000));
  expect(refresh).toHaveBeenCalledTimes(1);
  act(() => tree.unmount());
});

test('automatic refresh follows foreground state, uses the latest callback and cleans up on exit', () => {
  let onState!: (state: AppStateStatus) => void;
  const remove = jest.fn();
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener) => {
    onState = listener;
    return {remove};
  });
  const first = jest.fn();
  const latest = jest.fn();
  let tree!: ReactTestRenderer.ReactTestRenderer;
  const page = (
    onRefresh: () => void,
    loading = false,
    loadingMore = false,
  ) => (
    <ConversationsPage
      embedded
      outcome={outcome}
      loading={loading}
      loadingMore={loadingMore}
      onRefresh={onRefresh}
    />
  );
  act(() => {
    tree = ReactTestRenderer.create(page(first));
  });
  expect(first).toHaveBeenCalledTimes(1);
  act(() => jest.advanceTimersByTime(10000));
  act(() => tree.update(page(latest)));
  expect(latest).not.toHaveBeenCalled();
  act(() => jest.advanceTimersByTime(5000));
  expect(first).toHaveBeenCalledTimes(1);
  expect(latest).toHaveBeenCalledTimes(1);
  act(() => onState('background'));
  act(() => jest.advanceTimersByTime(30000));
  expect(latest).toHaveBeenCalledTimes(1);
  act(() => onState('active'));
  expect(latest).toHaveBeenCalledTimes(2);
  act(() => tree.update(page(latest, true)));
  act(() => jest.advanceTimersByTime(15000));
  expect(latest).toHaveBeenCalledTimes(2);
  act(() => tree.update(page(latest, false, true)));
  act(() => onState('active'));
  act(() => jest.advanceTimersByTime(15000));
  expect(latest).toHaveBeenCalledTimes(2);
  act(() => tree.update(page(latest)));
  act(() => jest.advanceTimersByTime(15000));
  expect(latest).toHaveBeenCalledTimes(3);
  act(() => tree.unmount());
  act(() => jest.advanceTimersByTime(30000));
  expect(latest).toHaveBeenCalledTimes(3);
  expect(remove).toHaveBeenCalledTimes(1);
});

test('automatic refresh does not disturb scrolled lists, open details or loaded older pages', () => {
  const refresh = jest.fn();
  const loadMore = jest.fn();
  let tree!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    tree = ReactTestRenderer.create(
      <ConversationsPage
        embedded
        outcome={{
          ...outcome,
          value: {
            ...outcome.value,
            page: {...outcome.value.page, hasMore: true, nextCursor: 'older'},
          },
        }}
        loading={false}
        onRefresh={refresh}
        onLoadMore={loadMore}
      />,
    );
  });
  const press = (label: string) =>
    act(() =>
      tree.root.findAllByProps({accessibilityLabel: label})[0].props.onPress(),
    );
  const scroll = (y: number) =>
    act(() =>
      tree.root
        .findByType(ScrollView)
        .props.onScroll({nativeEvent: {contentOffset: {y}}}),
    );
  expect(refresh).toHaveBeenCalledTimes(1);
  scroll(200);
  act(() => jest.advanceTimersByTime(15000));
  expect(refresh).toHaveBeenCalledTimes(1);
  scroll(0);
  act(() => jest.advanceTimersByTime(15000));
  expect(refresh).toHaveBeenCalledTimes(2);
  scroll(200);
  press('Open conversation Quiet workspace');
  act(() => jest.advanceTimersByTime(15000));
  expect(refresh).toHaveBeenCalledTimes(2);
  press('Back to conversations');
  act(() => jest.advanceTimersByTime(15000));
  expect(refresh).toHaveBeenCalledTimes(3);
  press('Load more conversations');
  expect(loadMore).toHaveBeenCalledTimes(1);
  scroll(0);
  act(() => jest.advanceTimersByTime(30000));
  expect(refresh).toHaveBeenCalledTimes(3);
  act(() => tree.unmount());
});

test('automatic refresh after remount does not replace a loaded older page', () => {
  const refresh = jest.fn();
  const loadMore = jest.fn();
  const page = (preserveLoadedPages: boolean) => (
    <ConversationsPage
      embedded
      outcome={{
        ...outcome,
        value: {
          ...outcome.value,
          page: {...outcome.value.page, hasMore: true, nextCursor: 'older'},
        },
      }}
      loading={false}
      onRefresh={refresh}
      onLoadMore={loadMore}
      preserveLoadedPages={preserveLoadedPages}
    />
  );
  let tree!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    tree = ReactTestRenderer.create(page(false));
  });
  expect(refresh).toHaveBeenCalledTimes(1);
  act(() =>
    tree.root
      .findAllByProps({accessibilityLabel: 'Load more conversations'})[0]
      .props.onPress(),
  );
  expect(loadMore).toHaveBeenCalledTimes(1);
  act(() => tree.unmount());
  act(() => {
    tree = ReactTestRenderer.create(page(true));
  });
  act(() => jest.advanceTimersByTime(15000));
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
