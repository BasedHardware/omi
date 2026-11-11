'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  deleteAllScreenFrames,
  deleteScreenFrame,
  getConversationScreenFrames,
  patchScreenFrameSharing,
} from '@/lib/api';
import { frameUrlRetryFloorMs, msUntilFrameUrlRefresh } from '@/lib/screenFrames';
import type { ConversationScreenFrameSet } from '@/types/conversation';

interface UseScreenFramesOptions {
  enabled?: boolean;
}

interface UseScreenFramesReturn {
  frameSet: ConversationScreenFrameSet | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  deleteFrame: (frameId: string) => Promise<boolean>;
  deleteAll: () => Promise<boolean>;
  setSharingEnabled: (enabled: boolean) => Promise<boolean>;
}

/** State is tagged with the conversation it belongs to, so it can never be shown under another. */
interface OwnedFrameState {
  conversationId: string | null;
  frameSet: ConversationScreenFrameSet | null;
  error: string | null;
  loading: boolean;
}

const EMPTY_STATE: OwnedFrameState = {
  conversationId: null,
  frameSet: null,
  error: null,
  loading: false,
};

/**
 * Loads and mutates a conversation's meeting-note screenshot set. Every
 * mutation replaces local state with the server's response rather than
 * predicting it locally (e.g. banner promotion after a delete is a
 * server-side decision — see `@/lib/screenFrames`).
 *
 * Two fences keep late responses out:
 * - Ownership: state carries its conversation id, and the returned values are
 *   derived as empty unless it matches the current id. A switch clears the
 *   previous set in the same render, and nothing for A can land under B.
 * - Generation, within one conversation: bumped when a load or mutation
 *   starts and when a mutation commits, but only while that conversation is
 *   current. A load or URL renewal applies its response only if the counter
 *   has not moved since it started, so no GET that overlapped a mutation can
 *   resurrect frames the mutation removed.
 */
export function useScreenFrames(
  conversationId: string | null,
  options: UseScreenFramesOptions = {},
): UseScreenFramesReturn {
  const { enabled = true } = options;
  const activeId = enabled ? conversationId : null;

  const [state, setState] = useState<OwnedFrameState>(EMPTY_STATE);
  // Consecutive renewals that did not adopt a fresh set (failed, or fenced out
  // by an overlapping mutation). Changing it rearms the renewal timer, with
  // backoff; any adopted set resets it.
  const [renewalMisses, setRenewalMisses] = useState(0);

  const lastUrlRefreshAt = useRef(0);
  const setGeneration = useRef(0);
  // Only the most recent load may end the loading state.
  const latestLoad = useRef(0);
  // Updated in a layout effect: synchronous with the commit, so no promise
  // can resolve between a switch rendering and the ref catching up.
  const currentIdRef = useRef(activeId);
  useLayoutEffect(() => {
    currentIdRef.current = activeId;
  }, [activeId]);

  const isCurrent = (id: string) => currentIdRef.current === id;
  /** Bumps the generation only for the current conversation's work. */
  const bumpIfCurrent = (id: string) => {
    if (isCurrent(id)) setGeneration.current += 1;
  };

  const owned = state.conversationId === activeId && activeId !== null;
  const frameSet = owned ? state.frameSet : null;
  const error = owned ? state.error : null;
  // A conversation whose load has not started yet is loading, not empty.
  const loading = activeId === null ? false : owned ? state.loading : true;

  const fetchFrames = useCallback(async () => {
    if (!activeId) {
      setState(EMPTY_STATE);
      return;
    }
    const requestedId = activeId;
    const generation = ++setGeneration.current;
    latestLoad.current = generation;
    lastUrlRefreshAt.current = Date.now();
    setRenewalMisses(0);
    setState((prev) =>
      prev.conversationId === requestedId
        ? { ...prev, loading: true, error: null }
        : { conversationId: requestedId, frameSet: null, error: null, loading: true },
    );
    try {
      const data = await getConversationScreenFrames(requestedId);
      if (isCurrent(requestedId) && setGeneration.current === generation) {
        setState({
          conversationId: requestedId,
          frameSet: data,
          error: null,
          loading: false,
        });
      }
    } catch (err) {
      console.error('Failed to fetch screen frames:', err);
      if (isCurrent(requestedId) && setGeneration.current === generation) {
        setState({
          conversationId: requestedId,
          frameSet: null,
          error: err instanceof Error ? err.message : 'Failed to load screenshots',
          loading: false,
        });
      }
    } finally {
      // A load fenced out by a mutation still ends the loading state, unless
      // a newer load has taken over.
      if (latestLoad.current === generation && isCurrent(requestedId)) {
        setState((prev) =>
          prev.conversationId === requestedId && prev.loading
            ? { ...prev, loading: false }
            : prev,
        );
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs are stable
  }, [activeId]);

  useEffect(() => {
    fetchFrames();
  }, [fetchFrames]);

  const refresh = useCallback(async () => {
    await fetchFrames();
  }, [fetchFrames]);

  // Signed URLs expire after 60 minutes. Swap in fresh ones shortly before,
  // silently (no loading flash), so a panel left open never shows dead images.
  useEffect(() => {
    if (!activeId) return;
    const due = msUntilFrameUrlRefresh(frameSet, Date.now());
    if (due === null) return;
    const sinceLast = Date.now() - lastUrlRefreshAt.current;
    const delay = Math.max(due, frameUrlRetryFloorMs(renewalMisses) - sinceLast);
    const requestedId = activeId;
    const timer = setTimeout(async () => {
      lastUrlRefreshAt.current = Date.now();
      const generation = setGeneration.current;
      try {
        const data = await getConversationScreenFrames(requestedId);
        if (!isCurrent(requestedId)) return;
        if (setGeneration.current === generation) {
          setRenewalMisses(0);
          setState((prev) =>
            prev.conversationId === requestedId
              ? { ...prev, frameSet: data, error: null }
              : prev,
          );
        } else {
          // Fenced out by a mutation. If that mutation adopted a set, the new
          // frameSet rearms the timer anyway; if it failed, nothing else will.
          setRenewalMisses((n) => n + 1);
        }
      } catch (err) {
        // Keep the current set (its URLs may still be valid); retry with backoff.
        console.error('Failed to refresh screen frame URLs:', err);
        if (isCurrent(requestedId)) setRenewalMisses((n) => n + 1);
      }
    }, delay);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs are stable
  }, [activeId, frameSet, renewalMisses]);

  const mutate = useCallback(
    async (
      request: (id: string) => Promise<ConversationScreenFrameSet>,
      failureMessage: string,
      logMessage: string,
    ): Promise<boolean> => {
      if (!activeId) return false;
      const requestedId = activeId;
      bumpIfCurrent(requestedId);
      try {
        const updated = await request(requestedId);
        if (isCurrent(requestedId)) {
          setGeneration.current += 1;
          setState((prev) =>
            prev.conversationId === requestedId
              ? { ...prev, frameSet: updated, error: null }
              : prev,
          );
        }
        return true;
      } catch (err) {
        console.error(logMessage, err);
        if (isCurrent(requestedId)) {
          setState((prev) =>
            prev.conversationId === requestedId
              ? { ...prev, error: err instanceof Error ? err.message : failureMessage }
              : prev,
          );
        }
        return false;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs are stable
    [activeId],
  );

  const deleteFrame = useCallback(
    (frameId: string) =>
      mutate(
        (id) => deleteScreenFrame(id, frameId),
        'Failed to delete screenshot',
        'Failed to delete screen frame:',
      ),
    [mutate],
  );

  const deleteAll = useCallback(
    () =>
      mutate(
        (id) => deleteAllScreenFrames(id),
        'Failed to delete screenshots',
        'Failed to delete all screen frames:',
      ),
    [mutate],
  );

  const setSharingEnabled = useCallback(
    (enabledValue: boolean) =>
      mutate(
        (id) => patchScreenFrameSharing(id, enabledValue),
        'Failed to update sharing',
        'Failed to update screen frame sharing:',
      ),
    [mutate],
  );

  return { frameSet, loading, error, refresh, deleteFrame, deleteAll, setSharingEnabled };
}
