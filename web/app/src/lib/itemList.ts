/**
 * `/items?conversation=<id>&task=<id>&memory=<id>`: an ordered list of items,
 * opened from an h.omi.me item-list link after sign-in.
 *
 * One query key per item, repeated; the order of the pairs is the display
 * order, so this reads the raw query string (URLSearchParams.get/getAll would
 * group repeated keys). Unknown keys are ignored and the list stops at
 * ITEM_LIST_MAX. Mirrors `web/frontend/src/lib/item-link.mjs`.
 */

export type ItemListKind = 'conversation' | 'task' | 'memory';

export interface ItemListEntry {
  kind: ItemListKind;
  id: string;
}

export const ITEM_LIST_MAX = 10;

const KINDS: readonly ItemListKind[] = ['conversation', 'task', 'memory'];
const ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;

function decodeQueryComponent(value: string): string {
  return decodeURIComponent(value.replace(/\+/g, ' '));
}

export function parseItemListQuery(query: string | null | undefined): ItemListEntry[] {
  const raw = String(query ?? '').replace(/^\?/, '');
  const items: ItemListEntry[] = [];
  const seen = new Set<string>();
  for (const pair of raw.split('&')) {
    if (items.length >= ITEM_LIST_MAX) break;
    const eq = pair.indexOf('=');
    if (eq <= 0) continue;
    let kind: string;
    let id: string;
    try {
      kind = decodeQueryComponent(pair.slice(0, eq));
      id = decodeQueryComponent(pair.slice(eq + 1)).trim();
    } catch {
      continue;
    }
    if (!KINDS.includes(kind as ItemListKind) || !ID_PATTERN.test(id)) continue;
    const key = `${kind}:${id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({ kind: kind as ItemListKind, id });
  }
  return items;
}

/**
 * The closest existing web view for an item: a conversation opens itself;
 * tasks and memories have list pages only, which scroll to and highlight the
 * item when it is loaded (`?highlight=<id>`).
 */
export function itemListHref({ kind, id }: ItemListEntry): string {
  const encoded = encodeURIComponent(id);
  switch (kind) {
    case 'conversation':
      return `/conversations?id=${encoded}`;
    case 'task':
      return `/tasks?highlight=${encoded}`;
    case 'memory':
      return `/memories?highlight=${encoded}`;
  }
}

/** The `highlight` id of the current page's query, read once on mount. */
export function readHighlightParam(search?: string): string | null {
  const source = search ?? (typeof window === 'undefined' ? '' : window.location.search);
  const id = new URLSearchParams(source).get('highlight')?.trim() ?? '';
  return ID_PATTERN.test(id) ? id : null;
}

/**
 * Where [id] sits in the Tasks list view: the flat index its row is focused
 * by (pending first, then completed), and whether Completed must be shown.
 */
export function taskListFocus(
  pending: readonly { id: string }[],
  completed: readonly { id: string }[],
  id: string,
): { index: number; completed: boolean } | null {
  const pendingIndex = pending.findIndex((task) => task.id === id);
  if (pendingIndex >= 0) return { index: pendingIndex, completed: false };
  const completedIndex = completed.findIndex((task) => task.id === id);
  if (completedIndex >= 0) {
    return { index: pending.length + completedIndex, completed: true };
  }
  return null;
}
