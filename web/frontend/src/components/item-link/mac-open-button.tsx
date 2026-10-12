'use client';

import { useEffect, useState } from 'react';

/**
 * "Open in Omi for Mac" on a Mac browser. iPadOS Safari sends a Mac user
 * agent, so a touch screen gets the iOS app link instead.
 */
export function MacOpenButton({
  href,
  touchHref,
  touchInstallHref,
}: {
  href: string;
  touchHref: string;
  touchInstallHref: string;
}) {
  const [isTouch, setIsTouch] = useState(false);
  useEffect(() => {
    setIsTouch(typeof navigator !== 'undefined' && navigator.maxTouchPoints > 1);
  }, []);
  if (isTouch) {
    // iPadOS Safari sends a Mac user agent. Offer the iOS app and the store,
    // the same pair a phone sees, not only the Mac scheme.
    return (
      <>
        <a
          href={touchHref}
          data-testid="item-link-open-mac"
          className="rounded-xl bg-white px-6 py-3 font-semibold text-[#0B0F17] transition-colors hover:bg-gray-200"
        >
          Open in the Omi App
        </a>
        <a
          href={touchInstallHref}
          data-testid="item-link-install"
          className="rounded-xl border border-white/20 px-6 py-3 font-semibold text-white transition-colors hover:bg-white/10"
        >
          Download on the App Store
        </a>
      </>
    );
  }
  return (
    <a
      href={href}
      data-testid="item-link-open-mac"
      className="rounded-xl bg-white px-6 py-3 font-semibold text-[#0B0F17] transition-colors hover:bg-gray-200"
    >
      Open in Omi for Mac
    </a>
  );
}
