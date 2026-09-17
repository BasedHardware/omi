import {useSyncExternalStore} from 'react';

const media =
  typeof window === 'undefined'
    ? null
    : window.matchMedia('(prefers-reduced-motion: reduce)');

// Subscribe by listener identity. RN Web 0.21 keys AccessibilityInfo handlers
// by function string, so one component's cleanup can remove another's listener.
function subscribe(listener: () => void) {
  media?.addEventListener('change', listener);
  return () => media?.removeEventListener('change', listener);
}

const snapshot = () => media?.matches ?? true;
const serverSnapshot = () => true;

export function useReduceMotion() {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}
