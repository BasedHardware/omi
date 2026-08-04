'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { scrollEdgesOf, type ScrollEdges } from '@/lib/scrollEdges';

/**
 * Whether a scroller has content hidden above or below the visible area.
 *
 * Fades that mark "there is more this way" have to be told when there isn't:
 * a top fade sitting over the first message, or a bottom fade over the last
 * one, dims content for no reason and reads as a rendering fault rather than
 * as an affordance.
 */

export function useScrollEdges<T extends HTMLElement>(): {
  ref: React.RefObject<T | null>;
  edges: ScrollEdges;
} {
  const ref = useRef<T>(null);
  // Both true at rest: an empty or unscrollable list has no hidden content in
  // either direction, so neither fade should show before the first measure.
  const [edges, setEdges] = useState<ScrollEdges>({ atTop: true, atBottom: true });

  const measure = useCallback(() => {
    const node = ref.current;
    if (!node) return;
    const next = scrollEdgesOf(node);
    setEdges((prev) =>
      prev.atTop === next.atTop && prev.atBottom === next.atBottom ? prev : next,
    );
  }, []);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    measure();
    node.addEventListener('scroll', measure, { passive: true });

    // Content arriving changes whether there is anything to scroll to, and it
    // arrives without a scroll event — a streaming reply grows the transcript
    // under a stationary scroll position.
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    for (const child of Array.from(node.children)) observer.observe(child);

    return () => {
      node.removeEventListener('scroll', measure);
      observer.disconnect();
    };
  }, [measure]);

  return { ref, edges };
}
