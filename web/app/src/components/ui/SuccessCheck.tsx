'use client';

import { useLayoutEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function SuccessCheck({
  active,
  children,
  className,
}: {
  active: boolean;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const path = ref.current?.querySelector('path');
    if (!path || typeof path.getTotalLength !== 'function') return;
    try {
      const len = Math.ceil(path.getTotalLength());
      path.style.strokeDasharray = String(len);
      path.style.strokeDashoffset = String(len);
    } catch {
      return;
    }
  }, [children]);

  return (
    <span
      ref={ref}
      className={cn('t-success-check', className)}
      data-state={active ? 'in' : 'out'}
      aria-hidden="true"
      style={
        {
          '--check-y-amount': '3px',
          '--check-blur-from': '2px',
          '--check-rotate-from': '25deg',
        } as CSSProperties
      }
    >
      {children}
    </span>
  );
}
