'use client';

import { useEffect, useLayoutEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function PanelReveal({
  children,
  className,
  open = true,
}: {
  children: ReactNode;
  className?: string;
  open?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!open) el.setAttribute('data-open', 'false');
  }, [open]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.setAttribute('data-open', open ? 'true' : 'false');
  }, [open]);

  return (
    <div
      ref={ref}
      className={cn('t-panel-slide', className)}
      data-open="false"
      style={{ '--panel-translate-y': '16px' } as CSSProperties}
    >
      {children}
    </div>
  );
}
