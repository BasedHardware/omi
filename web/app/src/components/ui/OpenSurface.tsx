'use client';

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from 'react';
import { cn } from '@/lib/utils';
import { prefersReducedMotion, readDurationToken } from '@/lib/transitionsDev';

function closeMs(className?: string): number {
  if (typeof className === 'string' && className.includes('t-modal')) {
    return readDurationToken('--modal-close-dur', 150);
  }
  return readDurationToken('--dropdown-close-dur', 150);
}

export function OpenSurface({
  open = true,
  onExited,
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  open?: boolean;
  onExited?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onExitedRef = useRef(onExited);
  onExitedRef.current = onExited;
  const [mounted, setMounted] = useState(open);
  const [phase, setPhase] = useState<'idle' | 'open' | 'closing'>('idle');

  useLayoutEffect(() => {
    if (open) setMounted(true);
  }, [open]);

  useLayoutEffect(() => {
    if (!mounted) return;
    const el = ref.current;
    const parent = el?.parentElement;
    const host = parent?.hasAttribute('data-state') ? parent : null;

    if (host) {
      const sync = () => {
        setPhase(host.getAttribute('data-state') === 'closed' ? 'closing' : 'open');
      };
      if (host.getAttribute('data-state') === 'closed') {
        setPhase('closing');
      }
      const observer = new MutationObserver(sync);
      observer.observe(host, { attributes: true, attributeFilter: ['data-state'] });
      return () => observer.disconnect();
    }

    setPhase(open ? 'idle' : 'closing');
  }, [mounted, open]);

  useEffect(() => {
    if (!mounted || !open) return;
    setPhase((current) => (current === 'closing' ? current : 'open'));
  }, [mounted, open]);

  useEffect(() => {
    if (open || !mounted) return;
    const finish = () => {
      setMounted(false);
      onExitedRef.current?.();
    };
    if (prefersReducedMotion()) {
      finish();
      return;
    }
    const el = ref.current;
    let finished = false;
    const once = () => {
      if (finished) return;
      finished = true;
      finish();
    };
    const onEnd = (event: TransitionEvent) => {
      if (event.target === el) once();
    };
    el?.addEventListener('transitionend', onEnd);
    const timer = window.setTimeout(once, closeMs(className) + 50);
    return () => {
      el?.removeEventListener('transitionend', onEnd);
      window.clearTimeout(timer);
    };
  }, [open, mounted, className]);

  if (!mounted) return null;

  return (
    <div
      ref={ref}
      className={cn(
        className,
        phase === 'open' && 'is-open',
        phase === 'closing' && 'is-closing',
      )}
      {...props}
    >
      {children}
    </div>
  );
}
