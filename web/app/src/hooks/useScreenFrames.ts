'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deleteAllScreenFrames,
  deleteScreenFrame,
  getConversationScreenFrames,
  patchScreenFrameSharing,
} from '@/lib/api';
import {
  MIN_FRAME_REFRESH_INTERVAL_MS,
  msUntilFrameUrlRefresh,
} from '@/lib/screenFrames';
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

/**
 * Loads and mutates a conversation's meeting-note screenshot set. Every
 * mutation replaces local state with the server's response rather than
 * predicting it locally (e.g. banner promotion after a delete is a
 * server-side decision — see `@/lib/screenFrames`).
 */
export function useScreenFrames(
  conversationId: string | null,
  options: UseScreenFramesOptions = {},
): UseScreenFramesReturn {
  const { enabled = true } = options;

  const [frameSet, setFrameSet] = useState<ConversationScreenFrameSet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // So an in-flight fetch/mutation for a conversation the user has since
  // navigated away from can't clobber the newer conversation's state.
  const lastUrlRefreshAt = useRef(0);
  // Bumped by every load and mutation. A background URL refresh applies its
  // response only if nothing replaced the set while it was in flight;
  // otherwise it would resurrect frames a delete had just removed.
  const setGeneration = useRef(0);
  const convIdRef = useRef(conversationId);
  useEffect(() => {
    convIdRef.current = conversationId;
  }, [conversationId]);

  const fetchFrames = useCallback(async () => {
    if (!enabled || !conversationId) {
      setFrameSet(null);
      setLoading(false);
      return;
    }

    const requestedId = conversationId;
    setGeneration.current += 1;
    lastUrlRefreshAt.current = Date.now();
    try {
      setLoading(true);
      setError(null);
      const data = await getConversationScreenFrames(requestedId);
      if (convIdRef.current === requestedId) {
        setFrameSet(data);
      }
    } catch (err) {
      if (convIdRef.current === requestedId) {
        setError(err instanceof Error ? err.message : 'Failed to load screenshots');
        setFrameSet(null);
      }
      console.error('Failed to fetch screen frames:', err);
    } finally {
      if (convIdRef.current === requestedId) {
        setLoading(false);
      }
    }
  }, [enabled, conversationId]);

  useEffect(() => {
    fetchFrames();
  }, [fetchFrames]);

  const refresh = useCallback(async () => {
    await fetchFrames();
  }, [fetchFrames]);

  // Signed URLs expire after 60 minutes. Swap in fresh ones shortly before,
  // silently (no loading flash), so a panel left open never shows dead images.
  useEffect(() => {
    if (!enabled || !conversationId) return;
    const due = msUntilFrameUrlRefresh(frameSet, Date.now());
    if (due === null) return;
    const sinceLast = Date.now() - lastUrlRefreshAt.current;
    const delay = Math.max(due, MIN_FRAME_REFRESH_INTERVAL_MS - sinceLast);
    const requestedId = conversationId;
    const timer = setTimeout(async () => {
      lastUrlRefreshAt.current = Date.now();
      const generation = setGeneration.current;
      try {
        const data = await getConversationScreenFrames(requestedId, { fresh: true });
        if (convIdRef.current === requestedId && setGeneration.current === generation) {
          setFrameSet(data);
        }
      } catch (err) {
        // Keep the current set; the next mount or manual refresh retries.
        console.error('Failed to refresh screen frame URLs:', err);
      }
    }, delay);
    return () => clearTimeout(timer);
  }, [enabled, conversationId, frameSet]);

  const deleteFrame = useCallback(
    async (frameId: string): Promise<boolean> => {
      if (!conversationId) return false;
      const requestedId = conversationId;
      setGeneration.current += 1;
      try {
        const updated = await deleteScreenFrame(requestedId, frameId);
        if (convIdRef.current === requestedId) {
          setFrameSet(updated);
          setError(null);
        }
        return true;
      } catch (err) {
        if (convIdRef.current === requestedId) {
          setError(err instanceof Error ? err.message : 'Failed to delete screenshot');
        }
        console.error('Failed to delete screen frame:', err);
        return false;
      }
    },
    [conversationId],
  );

  const deleteAll = useCallback(async (): Promise<boolean> => {
    if (!conversationId) return false;
    const requestedId = conversationId;
    setGeneration.current += 1;
    try {
      const updated = await deleteAllScreenFrames(requestedId);
      if (convIdRef.current === requestedId) {
        setFrameSet(updated);
        setError(null);
      }
      return true;
    } catch (err) {
      if (convIdRef.current === requestedId) {
        setError(err instanceof Error ? err.message : 'Failed to delete screenshots');
      }
      console.error('Failed to delete all screen frames:', err);
      return false;
    }
  }, [conversationId]);

  const setSharingEnabled = useCallback(
    async (enabledValue: boolean): Promise<boolean> => {
      if (!conversationId) return false;
      const requestedId = conversationId;
      setGeneration.current += 1;
      try {
        const updated = await patchScreenFrameSharing(requestedId, enabledValue);
        if (convIdRef.current === requestedId) {
          setFrameSet(updated);
          setError(null);
        }
        return true;
      } catch (err) {
        if (convIdRef.current === requestedId) {
          setError(err instanceof Error ? err.message : 'Failed to update sharing');
        }
        console.error('Failed to update screen frame sharing:', err);
        return false;
      }
    },
    [conversationId],
  );

  return { frameSet, loading, error, refresh, deleteFrame, deleteAll, setSharingEnabled };
}
