import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/firebase', () => ({ getIdToken: vi.fn() }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash: vi.fn() }));

import { findMemoriesByIds, type MemoriesPage } from '@/lib/api';
import {
  ITEM_LIST_MAX,
  itemListHref,
  parseItemListQuery,
  readHighlightParam,
  taskListFocus,
} from '@/lib/itemList';
import { safeNextPath, loginUrlReturningTo } from '@/lib/loginNext';

describe('parseItemListQuery', () => {
  it('keeps URL order across kinds and drops unknown keys, bad ids and repeats', () => {
    expect(
      parseItemListQuery(
        '?task=t-1&utm_source=x&conversation=c-1&memory=m-1&task=t-1&memory=..%2Fx&conversation=',
      ),
    ).toEqual([
      { kind: 'task', id: 't-1' },
      { kind: 'conversation', id: 'c-1' },
      { kind: 'memory', id: 'm-1' },
    ]);
    expect(parseItemListQuery('%zz=1&memory=%E0')).toEqual([]);
  });

  it('stops at ten items', () => {
    const items = parseItemListQuery(
      Array.from({ length: 12 }, (_, i) => `memory=m-${i}`).join('&'),
    );
    expect(items).toHaveLength(ITEM_LIST_MAX);
    expect(items.at(-1)?.id).toBe('m-9');
  });
});

describe('itemListHref', () => {
  it('opens the closest existing view for each kind', () => {
    expect(itemListHref({ kind: 'conversation', id: 'c-1' })).toBe(
      '/conversations?id=c-1',
    );
    expect(itemListHref({ kind: 'task', id: 't-1' })).toBe('/tasks?highlight=t-1');
    expect(itemListHref({ kind: 'memory', id: 'm-1' })).toBe('/memories?highlight=m-1');
  });
});

describe('highlight', () => {
  it('reads an opaque id only', () => {
    expect(readHighlightParam('?highlight=t-1')).toBe('t-1');
    expect(readHighlightParam('?highlight=%3Cscript%3E')).toBeNull();
    expect(readHighlightParam('')).toBeNull();
  });

  it('finds a task in the list view, pending first then completed', () => {
    const pending = [{ id: 'a' }, { id: 'b' }];
    const completed = [{ id: 'c' }];
    expect(taskListFocus(pending, completed, 'b')).toEqual({
      index: 1,
      completed: false,
    });
    expect(taskListFocus(pending, completed, 'c')).toEqual({ index: 2, completed: true });
    expect(taskListFocus(pending, completed, 'z')).toBeNull();
  });
});

describe('sign-in handoff', () => {
  it('returns to the /items list with its query intact', () => {
    expect(safeNextPath('/items?memory=m-1&conversation=c-1&memory=m-2')).toBe(
      '/items?memory=m-1&conversation=c-1&memory=m-2',
    );
    expect(loginUrlReturningTo('/items?task=t-1&memory=m-1')).toBe(
      '/login?next=%2Fitems%3Ftask%3Dt-1%26memory%3Dm-1',
    );
    expect(safeNextPath('//evil.example/items?task=t-1')).toBe('/home');
  });
});

describe('findMemoriesByIds', () => {
  const page = (ids: string[], extra: Partial<MemoriesPage> = {}): MemoriesPage => ({
    memories: ids.map((id) => ({ id, content: id } as MemoriesPage['memories'][number])),
    nextCursor: null,
    truncated: false,
    beliefEnabled: null,
    ...extra,
  });

  it('walks the owner-wide index and stops once every id is found', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page(['m-1', 'x'], { nextCursor: 'c1' }))
      .mockResolvedValueOnce(page(['m-2'], { nextCursor: 'c2' }));
    const { found, complete } = await findMemoriesByIds(['m-1', 'm-2'], { fetchPage });
    expect([...found.keys()]).toEqual(['m-1', 'm-2']);
    expect(complete).toBe(true);
    expect(fetchPage).toHaveBeenCalledTimes(2);
    expect(fetchPage.mock.calls[0][0]).toMatchObject({ view: 'all' });
  });

  it('reports an early stop as incomplete, so a missing id is not called deleted', async () => {
    const fetchPage = vi.fn().mockResolvedValue(page(['x'], { nextCursor: 'same' }));
    const capped = await findMemoriesByIds(['m-1'], { fetchPage, maxPages: 1 });
    expect(capped.complete).toBe(false);
    const truncated = await findMemoriesByIds(['m-1'], {
      fetchPage: vi.fn().mockResolvedValue(page([], { truncated: true })),
    });
    expect(truncated.complete).toBe(false);
    const exhausted = await findMemoriesByIds(['m-1'], {
      fetchPage: vi.fn().mockResolvedValue(page(['x'])),
    });
    expect(exhausted).toEqual({ found: new Map(), complete: true });
  });
});
