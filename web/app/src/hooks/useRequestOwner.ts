'use client';

import { useCallback, useEffect, useRef } from 'react';

/**
 * Ownership guard for async work that belongs to a selection.
 *
 * A hook keyed on a selection — the chat session being read, the goal being
 * shown — can have a request in flight when the selection changes. Without a
 * guard the late response commits into the new selection's state: the previous
 * thread's reply lands in the newly opened one, the previous goal's advice
 * appears under the new title, and the new selection's loading flag is cleared
 * by a request that was never its own.
 *
 * `claim()` at the start of a request and check `isCurrent()` before every
 * state write that follows an `await`. When the key has changed in the
 * meantime the write is dropped; the owner of the new key does its own work.
 */
export function useRequestOwner<K>(key: K): () => () => boolean {
  const keyRef = useRef(key);

  useEffect(() => {
    keyRef.current = key;
  }, [key]);

  return useCallback(() => {
    // Claims run from events and effects, never render, so the ref may be
    // written here — it closes the window where the effect above has not yet
    // caught up with a key that this render already sees.
    keyRef.current = key;
    return () => keyRef.current === key;
  }, [key]);
}
