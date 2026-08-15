/**
 * Platform deep-link for shared conversation pages (mirrors chat + tasks shares).
 * Kept as plain JS so node:test can import and assert branches without a TS loader.
 */

/**
 * @param {string} userAgent
 * @param {string} conversationId
 * @returns {string}
 */
export function getConversationSharePlatformLink(userAgent, conversationId) {
  const isAndroid = /android/i.test(userAgent);
  const isIOS = /iphone|ipad|ipod/i.test(userAgent);

  // iOS: custom scheme — Universal Links do not fire for same-domain taps on h.omi.me.
  // Android: intent:// with Play Store fallback when the app is missing.
  return isAndroid
    ? `intent://h.omi.me/conversations/${conversationId}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${encodeURIComponent(
        'https://play.google.com/store/apps/details?id=com.friend.ios',
      )};end`
    : isIOS
    ? `omi://h.omi.me/conversations/${conversationId}`
    : 'https://omi.me';
}
