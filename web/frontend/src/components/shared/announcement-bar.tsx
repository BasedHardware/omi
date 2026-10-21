'use client';

import { usePathname } from 'next/navigation';
import { isShareNotePath } from '@/src/lib/share-theme.mjs';

/** Elfsight announcement bar; shared conversations render without it. */
export default function AnnouncementBar() {
  const pathname = usePathname();
  if (isShareNotePath(pathname)) {
    return null;
  }
  return (
    <div
      className="elfsight-app-4df8bf4f-92a3-44bb-8bae-fcdac7faa58a"
      data-elfsight-app-lazy
    ></div>
  );
}
