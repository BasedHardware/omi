/**
 * Light/dark theme for public share pages.
 *
 * The system preference applies until the viewer picks a theme with the
 * toggle. The pick is stored per browser and written to
 * <html data-share-theme="light|dark">, which share-note.css reads.
 * Kept as plain JS so node:test can exercise it without a TS loader.
 */

export const SHARE_THEME_STORAGE_KEY = 'omi-share-theme';
export const SHARE_THEME_ATTRIBUTE = 'data-share-theme';

/** @param {unknown} value */
export function normalizeShareTheme(value) {
  return value === 'light' || value === 'dark' ? value : null;
}

/**
 * @param {string | null} stored the viewer's saved choice, if any
 * @param {boolean} systemPrefersDark
 * @returns {'light' | 'dark'}
 */
export function effectiveShareTheme(stored, systemPrefersDark) {
  return normalizeShareTheme(stored) ?? (systemPrefersDark ? 'dark' : 'light');
}

/** @param {'light' | 'dark'} theme */
export function toggledShareTheme(theme) {
  return theme === 'dark' ? 'light' : 'dark';
}

/**
 * Inline script that runs before the note paints so a saved choice never
 * flashes the other theme. Storage can throw (private mode, blocked site
 * data); the page then simply follows the system preference.
 */
export const SHARE_THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem('${SHARE_THEME_STORAGE_KEY}');if(t==='light'||t==='dark'){document.documentElement.setAttribute('${SHARE_THEME_ATTRIBUTE}',t);}}catch(e){}})();`;

/**
 * True for a shared-conversation page, which replaces the marketplace
 * header, footer and announcement bar with its own chrome. The browser path
 * is /conversations/:id; /memories/:id redirects there.
 *
 * @param {string | null | undefined} pathname
 */
export function isShareNotePath(pathname) {
  return /^\/(conversations|memories)\/[^/]+\/?$/.test(String(pathname || ''));
}
