/**
 * Private item links: https://h.omi.me/<kind>/<id> for kind conversation, task, memory.
 *
 * The app opens these through universal links / app links. This site only ever
 * serves a content-free fallback for them: it never fetches the item, because the
 * item is private and link previews (Apple, Telegram, Slack) fetch server-side
 * with no sign-in. The plural /conversations/<id> and /tasks/<token> pages are
 * public shares and are unrelated.
 *
 * Kept as plain JS so node:test can import it without a TS loader.
 */

export const ITEM_LINK_KINDS = /** @type {const} */ (['conversation', 'task', 'memory']);

export const WEB_APP_ORIGIN = 'https://app.omi.me';

const ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;

/**
 * @param {string} kind
 * @returns {kind is 'conversation' | 'task' | 'memory'}
 */
export function isItemLinkKind(kind) {
  return ITEM_LINK_KINDS.includes(/** @type {any} */ (kind));
}

/**
 * Ids are opaque server ids. Anything else is not one of our links.
 * @param {string} id
 */
export function isItemLinkId(id) {
  return typeof id === 'string' && ID_PATTERN.test(id);
}

/**
 * The signed-in web app page for an item. Conversations open the item itself;
 * tasks and memories have list pages only, so they land on the list.
 *
 * @param {'conversation' | 'task' | 'memory'} kind
 * @param {string} id
 * @returns {string} a path on the web app
 */
export function itemLinkWebAppPath(kind, id) {
  switch (kind) {
    case 'conversation':
      return `/conversations?id=${encodeURIComponent(id)}`;
    case 'task':
      return '/tasks';
    case 'memory':
      return '/memories';
    default:
      return '/home';
  }
}

/**
 * Sign-in handoff: the web app's login returns to `next` after sign-in (or at
 * once when already signed in).
 *
 * @param {'conversation' | 'task' | 'memory'} kind
 * @param {string} id
 * @param {{ origin?: string }} [options]
 */
export function itemLinkWebHandoff(kind, id, options = {}) {
  const origin = options.origin || WEB_APP_ORIGIN;
  return `${origin}/login?next=${encodeURIComponent(itemLinkWebAppPath(kind, id))}`;
}

/** Generic preview metadata: identical for every item, so nothing about it leaks. */
export const ITEM_LINK_METADATA = Object.freeze({
  title: { absolute: 'Omi' },
  description: 'Open this in the Omi app.',
  robots: { index: false, follow: false },
  openGraph: {
    title: 'Omi',
    description: 'Open this in the Omi app.',
    type: 'website',
    siteName: 'Omi',
  },
  twitter: { card: 'summary', title: 'Omi', description: 'Open this in the Omi app.' },
  other: {
    'apple-itunes-app': 'app-id=6502156163',
    'google-play-app': 'app-id=com.friend.ios',
  },
});

/*
 * Item lists: https://h.omi.me/items?conversation=<id>&task=<id>&memory=<id>
 *
 * One key per item, repeated; the order of the pairs in the URL is the display
 * order, so the raw query string is the source of truth (a parsed searchParams
 * object groups repeated keys and loses the interleaving). Unknown keys are
 * ignored and the list stops at ITEM_LIST_MAX. Same rule as the fallback above:
 * the page never reads the items.
 */

export const ITEM_LIST_MAX = 10;

/** Request header the proxy fills with the raw `/items` query (see src/proxy.ts). */
export const ITEM_LIST_QUERY_HEADER = 'x-omi-item-list-query';

/**
 * URL scheme of the released macOS app (codemagic.yaml sets URL_SCHEME="omi-computer"
 * for tagged stable builds; Omi Dev uses omi-computer-dev).
 */
export const MAC_APP_URL_SCHEME = 'omi-computer';

/**
 * @typedef {{ kind: 'conversation' | 'task' | 'memory', id: string }} ItemListEntry
 */

/** @param {string} value */
function decodeQueryComponent(value) {
  return decodeURIComponent(value.replace(/\+/g, ' '));
}

/**
 * The ordered `(kind, id)` pairs of an `/items` query string (with or without
 * the leading `?`). Unknown kinds, malformed ids and repeats are dropped.
 *
 * @param {string | null | undefined} query
 * @returns {ItemListEntry[]}
 */
export function parseItemListQuery(query) {
  const raw = String(query ?? '').replace(/^\?/, '');
  /** @type {ItemListEntry[]} */
  const items = [];
  const seen = new Set();
  for (const pair of raw.split('&')) {
    if (items.length >= ITEM_LIST_MAX) break;
    const eq = pair.indexOf('=');
    if (eq <= 0) continue;
    let kind;
    let id;
    try {
      kind = decodeQueryComponent(pair.slice(0, eq));
      id = decodeQueryComponent(pair.slice(eq + 1)).trim();
    } catch {
      continue;
    }
    if (!isItemLinkKind(kind) || !isItemLinkId(id)) continue;
    const key = `${kind}:${id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({ kind, id });
  }
  return items;
}

/**
 * Fallback when only a parsed searchParams object is available: keeps the order
 * within each kind, and kinds in first-seen order.
 *
 * @param {Record<string, string | string[] | undefined>} params
 * @returns {ItemListEntry[]}
 */
export function itemListFromSearchParams(params) {
  const pairs = [];
  for (const [key, value] of Object.entries(params || {})) {
    for (const one of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
      pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(one)}`);
    }
  }
  return parseItemListQuery(pairs.join('&'));
}

/**
 * Canonical query for a list: only recognised pairs, ids percent-encoded.
 * @param {ItemListEntry[]} items
 */
export function itemListQuery(items) {
  return items.map((item) => `${item.kind}=${encodeURIComponent(item.id)}`).join('&');
}

/**
 * The signed-in web app's list page for these items.
 * @param {ItemListEntry[]} items
 */
export function itemListWebAppPath(items) {
  return items.length ? `/items?${itemListQuery(items)}` : '/home';
}

/**
 * Sign-in handoff to the web app's `/items` page.
 * @param {ItemListEntry[]} items
 * @param {{ origin?: string }} [options]
 */
export function itemListWebHandoff(items, options = {}) {
  const origin = options.origin || WEB_APP_ORIGIN;
  return `${origin}/login?next=${encodeURIComponent(itemListWebAppPath(items))}`;
}

/**
 * Opens the list in the macOS app.
 * @param {ItemListEntry[]} items
 */
export function itemListMacDeepLink(items) {
  return `${MAC_APP_URL_SCHEME}://items?${itemListQuery(items)}`;
}

/**
 * A desktop Mac browser. iPadOS Safari also reports "Macintosh"; the page
 * corrects for that on the client (touch points), see MacOpenButton.
 * @param {string} userAgent
 */
export function isMacDesktopUserAgent(userAgent) {
  const ua = String(userAgent || '');
  return /Macintosh|Mac OS X/i.test(ua) && !/iPhone|iPad|iPod|Android/i.test(ua);
}

/**
 * Preview metadata for a list: the generic Omi card, with the item count only.
 * @param {number} count
 */
export function itemListMetadata(count) {
  const description =
    count > 0
      ? `${count} ${count === 1 ? 'item' : 'items'} in Omi`
      : ITEM_LINK_METADATA.description;
  return {
    ...ITEM_LINK_METADATA,
    description,
    openGraph: { ...ITEM_LINK_METADATA.openGraph, description },
    twitter: { ...ITEM_LINK_METADATA.twitter, description },
  };
}
