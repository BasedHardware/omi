import {useEffect, useRef, useState} from 'react';
import type {ReadsPhase} from './useDesktopReads';

/** One-shot Home cue after leaving Welcome/setup — never Claude MCP. */
export type PostSetupHomeCue = 'proven' | 'unavailable' | null;

/**
 * Arms only on an explicit Welcome/setup exit (`true → false`), not a cold
 * probe (`null → false`). Settles from real `readsPhase` so empty Home is
 * proven and unreachable Home stays the existing unavailable banner.
 */
export function usePostSetupHomeCue(
  onboardingRequired: boolean | null,
  readsPhase: ReadsPhase,
): PostSetupHomeCue {
  const [cue, setCue] = useState<PostSetupHomeCue>(null);
  const armedRef = useRef(false);
  const prevOnboardingRef = useRef(onboardingRequired);

  useEffect(() => {
    const previous = prevOnboardingRef.current;
    prevOnboardingRef.current = onboardingRequired;

    if (onboardingRequired === true) {
      armedRef.current = false;
      setCue(null);
      return;
    }

    if (previous === true && onboardingRequired === false) {
      armedRef.current = true;
      setCue(null);
    }
  }, [onboardingRequired]);

  useEffect(() => {
    if (!armedRef.current || cue != null) {
      return;
    }
    if (readsPhase === 'ready') {
      armedRef.current = false;
      setCue('proven');
      return;
    }
    if (
      readsPhase === 'unavailable' ||
      readsPhase === 'saved-but-refresh-failed'
    ) {
      armedRef.current = false;
      setCue('unavailable');
    }
  }, [cue, readsPhase]);

  return cue;
}
