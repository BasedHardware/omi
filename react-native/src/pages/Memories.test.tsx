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
jest.mock('../desktopReadClient', () => {
  const actual = jest.requireActual(
    '../desktopReadClient',
  ) as typeof import('../desktopReadClient');
  return {
    ...actual,
    loadMemories: (...args: unknown[]) => mockLoad(...args),
  };
});
jest.mock('../omiNative', () => ({omiBackend: {}}));
import {MemoriesPage} from './Memories';
import {
  clockLabel,
  desktopBackendUnavailableCopy,
  MemoryCursorExpiredError,
} from '../desktopReadClient';

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
const incompletePage: ReadPageState = {
  windowStatus: 'incomplete',
  complete: false,
  hasMore: false,
  nextCursor: null,
  completenessStatus: 'incomplete',
  reasons: ['accepted_work_pending'],
};
const textOf = (view: Renderer.ReactTestRenderer) =>
  view.root
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

test('memory grant denial shows the typed error instead of an empty library', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'error',
          error: 'This saved data is not available for this account.',
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(view)).toContain(
    'This saved data is not available for this account.',
  );
  expect(textOf(view)).not.toContain('No memories yet.');
});

test('nested non-retryable memory reads omit Refresh', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'error',
          error: desktopBackendUnavailableCopy,
        }}
        loading={false}
        onRefresh={jest.fn()}
      />,
    );
  });
  expect(textOf(view)).toContain(desktopBackendUnavailableCopy);
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh memories',
    ),
  ).toHaveLength(0);
});

test('retryable memory reads still offer Refresh', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
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
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh memories',
    ).length,
  ).toBeGreaterThan(0);
});

test('incomplete empty memories do not claim a complete library', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {items: [], page: incompletePage},
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(view)).toContain('Memories are incomplete.');
  expect(textOf(view)).not.toContain('No memories yet.');
});

test('degraded empty memories do not claim a complete library', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {
            items: [],
            page: {
              ...incompletePage,
              completenessStatus: 'degraded',
              reasons: ['projection_unavailable'],
            },
          },
        }}
        loading={false}
      />,
    );
  });
  expect(textOf(view)).toContain('Memories may be temporarily incomplete.');
  expect(textOf(view)).not.toContain('No memories yet.');
});

test('an incomplete empty memory search does not claim a complete miss', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {items: [], page: incompletePage},
        }}
        loading={false}
      />,
    );
  });
  try {
    act(() => {
      view.root
        .find(
          node => node.props.accessibilityLabel === 'Search loaded memories',
        )
        .props.onChangeText('nomatch');
    });
    expect(textOf(view)).toContain('Memories are incomplete.');
    expect(textOf(view)).not.toContain('No loaded memories match.');
  } finally {
    act(() => {
      view.unmount();
    });
  }
});

test('an expired memory cursor replaces the old page once and does not loop', async () => {
  mockLoad
    .mockRejectedValueOnce(new MemoryCursorExpiredError())
    .mockResolvedValueOnce({
      items: [memory('fresh-first')],
      page: page(null),
    });
  let view!: Renderer.ReactTestRenderer;
  await act(async () => {
    view = Renderer.create(
      <MemoriesPage
        outcome={outcome('kept-first', 'next-cursor')}
        loading={false}
      />,
    );
  });
  try {
    await act(async () => {
      button(view).props.onPress();
    });
    expect(mockLoad.mock.calls.map(call => call[1])).toEqual([
      'next-cursor',
      undefined,
    ]);
    expect(ids(view)).toEqual(['fresh-first']);
    expect(textOf(view)).toContain(
      'Memories changed. The list has been refreshed.',
    );
    expect(textOf(view)).not.toContain('More memories could not be loaded.');
    expect(ids(view)).not.toContain('kept-first');
  } finally {
    await act(async () => view.unmount());
  }
});

test('failed memory cursor recovery retains loaded rows and still offers Load more', async () => {
  mockLoad.mockRejectedValue(new MemoryCursorExpiredError());
  let view!: Renderer.ReactTestRenderer;
  await act(async () => {
    view = Renderer.create(
      <MemoriesPage
        outcome={outcome('kept-first', 'next-cursor')}
        loading={false}
      />,
    );
  });
  try {
    await act(async () => {
      button(view).props.onPress();
    });
    expect(mockLoad).toHaveBeenCalledTimes(2);
    expect(ids(view)).toEqual(['kept-first']);
    expect(textOf(view)).toContain('More memories could not be loaded.');
    expect(textOf(view)).toContain('Load more memories');
  } finally {
    await act(async () => view.unmount());
  }
});

test('generic later-page memory failures still offer Load more', async () => {
  mockLoad.mockRejectedValueOnce(new Error('memory page failed'));
  let view!: Renderer.ReactTestRenderer;
  await act(async () => {
    view = Renderer.create(
      <MemoriesPage
        outcome={outcome('kept-first', 'next-cursor')}
        loading={false}
      />,
    );
  });
  try {
    await act(async () => {
      button(view).props.onPress();
    });
    expect(textOf(view)).toContain('More memories could not be loaded.');
    expect(textOf(view)).toContain('Load more memories');
    expect(textOf(view)).not.toContain(desktopBackendUnavailableCopy);
    expect(ids(view)).toEqual(['kept-first']);
    expect(button(view)).toBeDefined();
  } finally {
    await act(async () => view.unmount());
  }
});

test('nested non-retryable later memory pages do not claim a load blip', async () => {
  mockLoad.mockRejectedValueOnce(new Error(desktopBackendUnavailableCopy));
  let view!: Renderer.ReactTestRenderer;
  await act(async () => {
    view = Renderer.create(
      <MemoriesPage
        outcome={outcome('kept-first', 'next-cursor')}
        loading={false}
      />,
    );
  });
  try {
    await act(async () => {
      button(view).props.onPress();
    });
    expect(textOf(view)).toContain(desktopBackendUnavailableCopy);
    expect(textOf(view)).not.toContain('More memories could not be loaded.');
    expect(textOf(view)).not.toContain('More memories are available.');
    expect(ids(view)).toEqual(['kept-first']);
    expect(
      view.root.findAll(
        node => node.props.accessibilityLabel === 'Load more memories',
      ),
    ).toHaveLength(0);
    act(() => {
      view.root
        .find(
          node => node.props.accessibilityLabel === 'Search loaded memories',
        )
        .props.onChangeText('nomatch');
    });
    expect(textOf(view)).toContain('No loaded memories match.');
    expect(textOf(view)).not.toContain('More memories are available.');
  } finally {
    await act(async () => view.unmount());
  }
});

test('omitted memory lineage does not claim Synthesized memory', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...memory('omitted-lineage'),
                provenance: {
                  label: null,
                  synthesisVersion: null,
                  inputDigest: null,
                  outputDigest: null,
                },
              },
              {
                ...memory('whitespace-lineage'),
                provenance: {
                  label: null,
                  synthesisVersion: ' \t\n',
                  inputDigest: 'a',
                  outputDigest: 'b',
                },
              },
              memory('present-lineage'),
            ],
            page: page(null),
          },
        }}
        loading={false}
      />,
    );
  });
  try {
    const copy = textOf(view);
    expect(copy).toContain('0 citations');
    expect(copy).toContain('Synthesized memory');
    expect(
      view.root.findAll(
        node =>
          node.type === Text && node.props.children === 'Synthesized memory',
      ),
    ).toHaveLength(1);
  } finally {
    act(() => view.unmount());
  }
});

test('empty memory bodies stay visible instead of a blank card', async () => {
  let view!: Renderer.ReactTestRenderer;
  await act(async () => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...memory('blank'),
                title: '',
                summary: '',
                searchableText: '',
              },
            ],
            page: page(null),
          },
        }}
        loading={false}
      />,
    );
  });
  try {
    expect(textOf(view)).toContain('Memory text unavailable');
    expect(
      view.root.find(
        node =>
          node.props.accessibilityLabel === 'Memory: Memory text unavailable',
      ),
    ).toBeDefined();
    act(() => {
      view.root
        .find(
          node => node.props.accessibilityLabel === 'Search loaded memories',
        )
        .props.onChangeText('unavailable');
    });
    expect(textOf(view)).toContain('Memory text unavailable');
    expect(textOf(view)).not.toContain('No loaded memories match.');
  } finally {
    await act(async () => view.unmount());
  }
});

test('a zero memory timestamp says Date unavailable instead of 1970', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {
            items: [{...memory('zero-date'), timestamp: 0}],
            page: page(null),
          },
        }}
        loading={false}
      />,
    );
  });
  try {
    expect(textOf(view)).toContain('Date unavailable');
    expect(textOf(view)).not.toContain('1970');
  } finally {
    act(() => view.unmount());
  }
});

test('Memories rows keep GET timestamps with the same clock as Home', () => {
  const timestamp = Date.parse('2026-09-07T12:00:00.000Z') / 1000;
  const expected = clockLabel(timestamp * 1000, Date.now());
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...memory('dated'),
                title: 'Visible memory',
                summary: 'Visible memory',
                searchableText: 'Visible memory',
                timestamp,
              },
            ],
            page: page(null),
          },
        }}
        loading={false}
      />,
    );
  });
  try {
    expect(expected).not.toBe('');
    expect(textOf(view)).toContain(expected);
    expect(textOf(view)).not.toContain('Date unavailable');
  } finally {
    act(() => view.unmount());
  }
});

test('Memories rows name GET ledger slot, playbook body, baseline, and known devices', () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...memory('ledger'),
                title: 'Prefers concise recaps.',
                summary: 'Prefers concise recaps.',
                searchableText: 'Prefers concise recaps.',
                provenance: {
                  label: null,
                  synthesisVersion: null,
                  inputDigest: null,
                  outputDigest: null,
                },
                ledgerSlot: 'identity.full_name',
                ledgerBody: 'Open with the weekly recap.',
                isBaseline: true,
                captureDeviceLabel: 'Mac',
              },
              {
                ...memory('omitted'),
                title: 'Likes walking.',
                summary: 'Likes walking.',
                searchableText: 'Likes walking.',
                provenance: {
                  label: null,
                  synthesisVersion: null,
                  inputDigest: null,
                  outputDigest: null,
                },
              },
            ],
            page: page(null),
          },
        }}
        loading={false}
      />,
    );
  });
  try {
    const copy = textOf(view);
    expect(copy).toContain('identity.full_name');
    expect(copy).toContain('Open with the weekly recap.');
    expect(copy).toContain('Baseline Memory');
    expect(copy).toContain('Mac');
    expect(
      view.root.findAll(
        node => node.type === Text && node.props.children === 'Baseline Memory',
      ),
    ).toHaveLength(1);
  } finally {
    act(() => view.unmount());
  }
});
