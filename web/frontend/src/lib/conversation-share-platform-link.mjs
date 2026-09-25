/**
 * Platform deep-links for public Omi web pages (shares, unlimited, wrapped).
 * Kept as plain JS so node:test can import and assert branches without a TS loader.
 */

import { shareHost } from './share-base-url.mjs';

const PLAY_STORE =
  'https://play.google.com/store/apps/details?id=com.friend.ios';

/**
 * @param {string} userAgent
 * @param {string} path path under the share host without a leading slash (e.g. "unlimited", "conversations/abc")
 * @param {{ shareHost?: string }} [options]
 * @returns {string}
 */
export function getOmiPlatformDeepLink(userAgent, path, options = {}) {
  const normalized = String(path || '')
    .replace(/^\/+/, '')
    .replace(/\/+$/, '');
  if (!normalized) {
    return 'https://omi.me';
  }

  const host = options.shareHost || shareHost();
  const isAndroid = /android/i.test(userAgent);
  const isIOS = /iphone|ipad|ipod/i.test(userAgent);

  // iOS: custom scheme — Universal Links do not fire for same-domain taps.
  // Android: intent:// with Play Store fallback when the app is missing.
  return isAndroid
    ? `intent://${host}/${normalized}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${encodeURIComponent(
        PLAY_STORE,
      )};end`
    : isIOS
      ? `omi://${host}/${normalized}`
      : 'https://omi.me';
}

/**
 * @param {string} userAgent
 * @param {string} conversationId
 * @param {{ shareHost?: string }} [options]
 * @returns {string}
 */
export function getConversationSharePlatformLink(userAgent, conversationId, options = {}) {
  return getOmiPlatformDeepLink(userAgent, `conversations/${conversationId}`, options);
}
