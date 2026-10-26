'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from '@tschk/moonshine-next/link';
import { useSearchParams } from '@tschk/moonshine-next/navigation';
import { Brain, GanttChartSquare, ListChecks } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { findMemoriesByIds, getActionItem, getConversation } from '@/lib/api';
import {
  itemListHref,
  itemListMemoryTitle,
  itemListTaskPresentation,
  parseItemListQuery,
  type ItemListEntry,
  type ItemListKind,
} from '@/lib/itemList';
import { cn } from '@/lib/utils';
import { conversationDisplayTitle } from '@/lib/conversationTitle';

/** A loaded row: its title, or why it cannot be shown. */
export type ItemListRowState =
  | { status: 'loading' }
  | { status: 'ready'; title: string; completed?: boolean }
  | { status: 'unavailable' }
  /** Not found in the part of the memory index read; it may still exist. */
  | { status: 'unresolved' };

export interface ItemListLoaders {
  conversation: (id: string) => Promise<{ title: string } | null>;
  task: (id: string) => Promise<{ title: string; completed: boolean } | null>;
  memories: (ids: string[]) => Promise<{
    found: Map<string, { title: string }>;
    complete: boolean;
    /** Found, but not default-visible (archived, locked, deleted, empty). */
    hidden?: ReadonlySet<string>;
  }>;
}

const defaultLoaders: ItemListLoaders = {
  conversation: async (id) => {
    const conversation = await getConversation(id);
    const title = conversationDisplayTitle(conversation).trim();
    return { title: title || 'Untitled conversation' };
  },
  task: async (id) => {
    const task = await getActionItem(id);
    return itemListTaskPresentation(task);
  },
  memories: async (ids) => {
    const { found, complete } = await findMemoriesByIds(ids);
    const titles = new Map<string, { title: string }>();
    const hidden = new Set<string>();
    for (const [id, memory] of found) {
      // Default memory access is Short-term + Long-term (INV-MEM-1); an archived
      // memory is not opened from a link, matching the app's single-memory link.
      const title = itemListMemoryTitle(memory);
      if (title) titles.set(id, { title });
      else hidden.add(id);
    }
    return { found: titles, hidden, complete };
  },
};

const KIND_CHROME: Record<ItemListKind, { label: string; icon: typeof Brain }> = {
  // The sidebar's icons for each destination.
  conversation: { label: 'Conversation', icon: GanttChartSquare },
  task: { label: 'Task', icon: ListChecks },
  memory: { label: 'Memory', icon: Brain },
};

const rowKey = (item: ItemListEntry) => `${item.kind}:${item.id}`;

/**
 * The items of an h.omi.me item-list link, in link order. Each row opens the
 * closest existing view; an item that is gone or not the reader's stays in
 * place as a muted "No longer available" row.
 */
export function ItemListPage({
  loaders = defaultLoaders,
}: {
  loaders?: ItemListLoaders;
}) {
  const query = useSearchParams()?.toString() ?? '';
  const items = useMemo(() => parseItemListQuery(query), [query]);
  const [rows, setRows] = useState<Record<string, ItemListRowState>>({});

  useEffect(() => {
    let cancelled = false;
    const set = (key: string, state: ItemListRowState) => {
      if (!cancelled) setRows((prev) => ({ ...prev, [key]: state }));
    };
    setRows({});
    for (const item of items) {
      if (item.kind === 'conversation') {
        loaders
          .conversation(item.id)
          .then((r) =>
            set(rowKey(item), r ? { status: 'ready', ...r } : { status: 'unavailable' }),
          )
          .catch(() => set(rowKey(item), { status: 'unavailable' }));
      } else if (item.kind === 'task') {
        loaders
          .task(item.id)
          .then((r) =>
            set(rowKey(item), r ? { status: 'ready', ...r } : { status: 'unavailable' }),
          )
          .catch(() => set(rowKey(item), { status: 'unavailable' }));
      }
    }
    const memoryItems = items.filter((item) => item.kind === 'memory');
    if (memoryItems.length > 0) {
      loaders
        .memories(memoryItems.map((item) => item.id))
        .then(({ found, complete, hidden }) => {
          for (const item of memoryItems) {
            const hit = found.get(item.id);
            // A row we already classified as hidden stays unavailable even when
            // the index walk stopped early. Only an id we never saw may still exist.
            const concealed = hidden?.has(item.id) ?? false;
            set(
              rowKey(item),
              hit?.title
                ? { status: 'ready', title: hit.title }
                : concealed || complete
                ? { status: 'unavailable' }
                : { status: 'unresolved' },
            );
          }
        })
        .catch(() => {
          for (const item of memoryItems) set(rowKey(item), { status: 'unresolved' });
        });
    }
    return () => {
      cancelled = true;
    };
  }, [items, loaders]);

  const title =
    items.length === 0
      ? 'No Items'
      : `${items.length} ${items.length === 1 ? 'Item' : 'Items'}`;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader title={title} />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-2xl px-4 py-6">
          {items.length === 0 ? (
            <p
              data-testid="item-list-empty"
              className="text-center text-sm text-text-secondary"
            >
              This link has no items to show.
            </p>
          ) : (
            <ol className="space-y-2" data-testid="item-list">
              {items.map((item, index) => (
                <li key={rowKey(item)}>
                  <ItemListRow
                    item={item}
                    index={index}
                    state={rows[rowKey(item)] ?? { status: 'loading' }}
                  />
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

function ItemListRow({
  item,
  index,
  state,
}: {
  item: ItemListEntry;
  index: number;
  state: ItemListRowState;
}) {
  const { label, icon: Icon } = KIND_CHROME[item.kind];
  const eyebrow = (
    <span className="flex items-center gap-1.5 text-xs font-semibold text-text-secondary">
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
    </span>
  );
  const card = 'block rounded-xl border border-bg-tertiary bg-bg-secondary px-4 py-3';

  if (state.status === 'loading') {
    return (
      <div className={card} data-testid={`item-list-loading-${index}`} aria-busy>
        {eyebrow}
        <div className="mt-2 h-4 w-2/3 animate-pulse rounded bg-bg-tertiary" />
      </div>
    );
  }
  if (state.status === 'unavailable') {
    return (
      <div
        className={cn(card, 'opacity-70')}
        data-testid={`item-list-unavailable-${index}`}
      >
        {eyebrow}
        <p className="mt-1 text-sm text-text-secondary">No longer available</p>
      </div>
    );
  }
  // Only a memory can be unresolved: it was not in the part of the index read.
  const text = state.status === 'ready' ? state.title : 'Open in Memories';
  return (
    <Link
      href={itemListHref(item)}
      data-testid={`item-list-row-${index}`}
      className={cn(card, 'transition-colors hover:bg-bg-tertiary')}
    >
      {eyebrow}
      <p
        className={cn(
          'mt-1 line-clamp-3 text-sm text-text-primary',
          state.status === 'ready' &&
            state.completed &&
            'text-text-secondary line-through',
          state.status === 'unresolved' && 'text-text-secondary',
        )}
      >
        {text}
      </p>
    </Link>
  );
}
