'use client';

import { useLayoutEffect, useRef, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function OpenSurface({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.classList.remove('is-closing');
    el.classList.add('is-open');
    return () => {
      el.classList.remove('is-open');
      el.classList.add('is-closing');
    };
  }, []);

  return (
    <div ref={ref} className={cn(className)} {...props}>
      {children}
    </div>
  );
}
