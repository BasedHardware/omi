import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {FlatList, Text} from 'react-native';
import type {
  DomainRead,
  DomainReadOutcome,
  MemoryProjection,
  ReadPageState,
} from '../desktopReadClient';

const mockLoad = jest.fn();
jest.mock('../desktopReadClient', () => ({
  loadMemories: (...args: unknown[]) => mockLoad(...args),
}));
jest.mock('../omiNative', () => ({omiBackend: {}}));
import {MemoriesPage} from './Memories';

const page = (cursor: string | null): ReadPageState => ({
  windowStatus: cursor ? 'more' : 'complete',
  complete: !cursor,
  hasMore: !!cursor,
  nextCursor: cursor,
  completenessStatus: 'complete',
  reasons: [],
});
const memory = (id: string): MemoryProjection => ({
  kind: 'memory',
  id,
  title: id,
  summary: id,
  searchableText: id,
  citations: [],
  timestamp: null,
  provenance: {
    label: null,
    synthesisVersion: '1',
    inputDigest: 'a',
    outputDigest: 'b',
  },
});
const outcome = (
  id: string,
  cursor: string | null,
): DomainReadOutcome<MemoryProjection> => ({
  status: 'success',
  value: {items: [memory(id)], page: page(cursor)},
});
const deferred = () => {
  let resolve!: (value: DomainRead<MemoryProjection>) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<DomainRead<MemoryProjection>>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return {promise, resolve, reject};
};
const button = (view: Renderer.ReactTestRenderer) =>
  view.root.findAll(
    node => node.props.accessibilityLabel === 'Load more memories',
  )[0]!;
const ids = (view: Renderer.ReactTestRenderer) =>
  (view.root.findByType(FlatList).props.data as MemoryProjection[]).map(
    item => item.id,
  );
beforeEach(() => mockLoad.mockReset());

test.each(['resolve', 'reject'] as const)(
  'a retired page %s cannot change refreshed memories or its pending request',
  async mode => {
    const old = deferred(),
      fresh = deferred();
    mockLoad
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise);
    let view!: Renderer.ReactTestRenderer;
    await act(async () => {
      view = Renderer.create(
        <MemoriesPage
          outcome={outcome('old-first', 'old-cursor')}
          loading={false}
        />,
      );
    });
    try {
      act(() => {
        button(view).props.onPress();
        button(view).props.onPress();
      });
      expect(mockLoad).toHaveBeenCalledTimes(1);
      await act(async () => {
        view.update(
          <MemoriesPage
            outcome={outcome('fresh-first', 'fresh-cursor')}
            loading={false}
          />,
        );
      });
      act(() => {
        button(view).props.onPress();
      });
      expect(mockLoad).toHaveBeenLastCalledWith({}, 'fresh-cursor');
      await act(async () => {
        if (mode === 'resolve') {
          old.resolve({items: [memory('stale-second')], page: page(null)});
        } else {
          old.reject(new Error('old request failed'));
        }
      });
      expect(ids(view)).toEqual(['fresh-first']);
      expect(button(view).props.disabled).toBe(true);
      expect(
        view.root.findAll(
          node =>
            node.type === Text &&
            node.props.children === 'More memories could not be loaded.',
        ),
      ).toHaveLength(0);
      await act(async () => {
        fresh.resolve({items: [memory('fresh-second')], page: page(null)});
      });
      expect(ids(view)).toEqual(['fresh-first', 'fresh-second']);
    } finally {
      await act(async () => view.unmount());
    }
  },
);

test('retiring the read outcome clears loaded memories and ignores its delayed page', async () => {
  const pending = deferred();
  mockLoad.mockReturnValueOnce(pending.promise);
  let view!: Renderer.ReactTestRenderer;
  await act(async () => {
    view = Renderer.create(
      <MemoriesPage
        outcome={outcome('private-first', 'private-cursor')}
        loading={false}
      />,
    );
  });
  try {
    act(() => {
      button(view).props.onPress();
    });
    await act(async () => {
      view.update(<MemoriesPage outcome={null} loading={false} />);
    });
    await act(async () => {
      pending.resolve({items: [memory('private-second')], page: page(null)});
    });
    expect(ids(view)).toEqual([]);
    expect(
      view.root.findAll(
        node => node.props.accessibilityLabel === 'Load more memories',
      ),
    ).toHaveLength(0);
  } finally {
    await act(async () => view.unmount());
  }
});
