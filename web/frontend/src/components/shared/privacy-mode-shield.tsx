'use client';

/**
 * Small shield indicator surfaced in the app header when the authenticated
 * user has EU Privacy Mode enabled. Mirrors the desktop's status-bar shield
 * (see desktop/Desktop/Sources/OmiApp.swift::applyMenuBarPrivacyShield).
 *
 * Behavior:
 * - Hidden when the user is anonymous, when Privacy Mode is off, or while
 *   the snapshot is loading. No layout shift in the header chrome.
 * - Re-fetches the snapshot whenever the window regains focus so a toggle
 *   in /settings reflects in the header without a full page reload.
 *
 * Renders a single SF-Symbols-style "shield" glyph + accessible label.
 * Intentionally subtle — the EU Privacy claim is communicated by the
 * /settings card; this is a passive indicator, not a CTA.
 */

import { useEffect, useState } from 'react';
import { useAuth } from '@/src/hooks/useAuth';
import { fetchSettingsSnapshot } from '@/src/app/settings/actions';

export default function PrivacyModeShield() {
  const { user, isAuthenticated } = useAuth();
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !user) {
      setEnabled(null);
      return;
    }

    let cancelled = false;
    const refresh = () => {
      fetchSettingsSnapshot(user.uid)
        .then((snap) => {
          if (!cancelled) setEnabled(snap.eu_privacy_mode);
        })
        .catch(() => {
          if (!cancelled) setEnabled(null);
        });
    };

    refresh();
    window.addEventListener('focus', refresh);
    return () => {
      cancelled = true;
      window.removeEventListener('focus', refresh);
    };
  }, [isAuthenticated, user]);

  if (!enabled) return null;

  return (
    <span
      role="status"
      aria-label="EU Privacy Mode is on"
      title="EU Privacy Mode is on — AI traffic routes through regolo.ai (Italy)"
      className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-500"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="currentColor"
        className="h-3.5 w-3.5"
        aria-hidden="true"
      >
        <path d="M12 2 4 5v6c0 5 3.5 9.5 8 11 4.5-1.5 8-6 8-11V5l-8-3zm0 2.18 6 2.25v4.57c0 4.07-2.74 7.83-6 9.07-3.26-1.24-6-5-6-9.07V6.43l6-2.25z" />
      </svg>
      EU Privacy
    </span>
  );
}
