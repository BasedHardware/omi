'use client';

import { useEffect, useState } from 'react';

/**
 * "Open in Omi for Mac" on a Mac browser. iPadOS Safari sends a Mac user
 * agent, so a touch screen gets the iOS app link instead.
 */
export function MacOpenButton({ href, touchHref }: { href: string; touchHref: string }) {
  const [isTouch, setIsTouch] = useState(false);
  useEffect(() => {
    setIsTouch(typeof navigator !== 'undefined' && navigator.maxTouchPoints > 1);
  }, []);
  return (
    <a
      href={isTouch ? touchHref : href}
      data-testid="item-link-open-mac"
      className="rounded-xl bg-white px-6 py-3 font-semibold text-[#0B0F17] transition-colors hover:bg-gray-200"
    >
      {isTouch ? 'Open in the Omi App' : 'Open in Omi for Mac'}
    </a>
  );
}
