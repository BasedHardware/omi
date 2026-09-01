'use client';

import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function PageSlide({
  pageKey,
  children,
  className,
}: {
  pageKey: string;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.setAttribute('data-page', '1');
    void el.offsetWidth;
    el.setAttribute('data-page', '2');
  }, [pageKey]);

  return (
    <div ref={ref} className={cn('t-page-slide h-full', className)} data-page="1">
      <section className="t-page" data-page-id="2">
        {children}
      </section>
    </div>
  );
}
