'use client';

import {
  SHARE_THEME_ATTRIBUTE,
  SHARE_THEME_STORAGE_KEY,
  effectiveShareTheme,
  toggledShareTheme,
} from '@/src/lib/share-theme.mjs';

/**
 * Flips the share page between light and dark. Both icons render on the
 * server and CSS shows the right one, so the button never mismatches on
 * hydration or flashes before the stored choice is read.
 */
export default function ShareThemeToggle() {
  const toggle = () => {
    const root = document.documentElement;
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const next = toggledShareTheme(
      effectiveShareTheme(root.getAttribute(SHARE_THEME_ATTRIBUTE), systemPrefersDark),
    );
    root.setAttribute(SHARE_THEME_ATTRIBUTE, next);
    try {
      localStorage.setItem(SHARE_THEME_STORAGE_KEY, next);
    } catch {
      // Storage blocked: the choice lasts for this page view only.
    }
  };

  return (
    <button
      type="button"
      className="sn-icon-btn"
      onClick={toggle}
      aria-label="Switch between light and dark"
      title="Switch between light and dark"
    >
      <svg
        className="sn-only-light"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
      </svg>
      <svg
        className="sn-only-dark"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    </button>
  );
}
