'use client';

import { useState, useEffect } from 'react';

export function BetaRibbon() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Don't render on server to avoid hydration issues
  if (!mounted) return null;

  // Don't show on mobile (overlay handles it)
  if (typeof window !== 'undefined' && window.innerWidth < 1024) return null;

  return (
    <div className="fixed top-0 right-0 z-[9998] overflow-hidden pointer-events-none w-32 h-32">
      <a
        href="https://feedback.omi.me"
        target="_blank"
        rel="noopener noreferrer"
        className="pointer-events-auto absolute top-6 -right-8 w-36 text-center py-1.5 bg-purple-primary text-white text-xs font-semibold uppercase tracking-wider rotate-45 shadow-lg hover:bg-purple-600 transition-colors"
      >
        Beta
      </a>
    </div>
  );
}
