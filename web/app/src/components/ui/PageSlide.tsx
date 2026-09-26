'use client';

import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { prefersReducedMotion, readDurationToken } from '@/lib/transitionsDev';

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
  const pageRef = useRef<HTMLElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.removeAttribute('data-settled');
    el.setAttribute('data-page', '1');
    void el.offsetWidth;
    el.setAttribute('data-page', '2');

    if (prefersReducedMotion()) {
      el.setAttribute('data-settled', '');
      return;
    }

    const page = pageRef.current;
    const settle = () => el.setAttribute('data-settled', '');
    page?.addEventListener('transitionend', settle);
    const timer = window.setTimeout(settle, readDurationToken('--page-slide-dur', 250) + 80);
    return () => {
      page?.removeEventListener('transitionend', settle);
      window.clearTimeout(timer);
    };
  }, [pageKey]);

  return (
    <div ref={ref} className={cn('t-page-slide h-full', className)} data-page="1">
      <section ref={pageRef} className="t-page" data-page-id="2">
        {children}
      </section>
    </div>
  );
}
