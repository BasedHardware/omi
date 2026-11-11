/**
 * Public share / web origin for self-hosting (#4339).
 * Matches backend OMI_SHARE_BASE_URL and Flutter/desktop share helpers.
 * Kept as plain JS so node:test can assert without a TS loader.
 */

export const DEFAULT_SHARE_BASE_URL = 'https://h.omi.me';

/**
 * @param {string | undefined | null} raw
 * @returns {string} origin (+ optional path prefix), no trailing slash
 */
export function shareBaseUrl(raw = process.env.WEB_URL) {
  let value = String(raw ?? '').trim();
  if (!value) value = DEFAULT_SHARE_BASE_URL;
  if (!value.includes('://')) value = `https://${value}`;

  let url;
  try {
    url = new URL(value);
  } catch {
    return DEFAULT_SHARE_BASE_URL;
  }

  if (
    !['http:', 'https:'].includes(url.protocol) ||
    !url.hostname ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    return DEFAULT_SHARE_BASE_URL;
  }

  const origin = url.port
    ? `${url.protocol}//${url.hostname}:${url.port}`
    : `${url.protocol}//${url.hostname}`;
  const path = url.pathname.replace(/\/+$/, '');
  if (!path || path === '/') return origin;
  return `${origin}${path}`;
}

/**
 * Hostname used in intent:// / omi:// deep links.
 * @param {string | undefined | null} raw
 * @returns {string}
 */
export function shareHost(raw = process.env.WEB_URL) {
  try {
    return new URL(shareBaseUrl(raw)).hostname;
  } catch {
    return 'h.omi.me';
  }
}
