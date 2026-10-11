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
