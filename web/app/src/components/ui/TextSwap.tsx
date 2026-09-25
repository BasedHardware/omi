'use client';

import { useEffect, useLayoutEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { prefersReducedMotion, readDurationToken } from '@/lib/transitionsDev';

export function TextSwap({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const [display, setDisplay] = useState(text);
  const [phase, setPhase] = useState<'idle' | 'exit' | 'enter-start'>('idle');

  useEffect(() => {
    if (text === display) {
      if (phase !== 'idle') setPhase('idle');
      return;
    }
    if (prefersReducedMotion()) {
      setDisplay(text);
      setPhase('idle');
      return;
    }
    setPhase('exit');
    const dur = readDurationToken('--text-swap-dur', 150);
    const timer = window.setTimeout(() => {
      setDisplay(text);
      setPhase('enter-start');
    }, dur);
    return () => window.clearTimeout(timer);
  }, [text, display, phase]);

  useLayoutEffect(() => {
    if (phase !== 'enter-start') return;
    void document.body.offsetHeight;
    setPhase('idle');
  }, [phase]);

  return (
    <span
      className={cn(
        't-text-swap',
        phase === 'exit' && 'is-exit',
        phase === 'enter-start' && 'is-enter-start',
        className,
      )}
    >
      {display}
    </span>
  );
}
