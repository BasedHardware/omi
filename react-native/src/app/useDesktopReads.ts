import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  loadDesktopReads,
  projectionTimestamp,
  desktopBackendConfigurationCopy,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
} from '../desktopReadClient';
import {omiBackend} from '../omiNative';

export type ProjectionFilter = 'all' | DesktopReadProjection['kind'];
export type ReadsPhase =
  | 'initial-loading'
  | 'refreshing'
  | 'ready'
  | 'saved-but-refresh-failed'
  | 'unavailable';

export function useDesktopReads({enabled}: {enabled: boolean}) {
  const [readOutcomes, setReadOutcomes] = useState<DesktopReadOutcomes | null>(
    null,
  );
  const readOutcomesRef = useRef<DesktopReadOutcomes | null>(null);
  // Tracks whether Home ever presented saved rows, independent of the latest
  // refresh outcome, so a failed first load followed by a retry stays truthful.
  const homeReadsLoadedRef = useRef(false);
  const [readsPhase, setReadsPhase] = useState<ReadsPhase>('initial-loading');
  // Monotonic refresh sequence. Every gate transition and every new refresh
  // bumps it, so a refresh that started under a previous session (or before a
  // newer refresh) can never write rows or phase into the session that
  // follows — including the merge source that "saved data" phases read from.
  const refreshSeqRef = useRef(0);

  // Cloud reads only run for a ready session. Signed-out and probing Macs
  // never hit /v1/conversations|memories|tasks, so their 401/unconfigured
  // failures cannot poison readsPhase for the session that signs in next.
  const refreshReads = useCallback(
    async (initial: boolean) => {
      if (!enabled) {
        return;
      }
      const backend = omiBackend;
      if (backend === undefined || backend === null) {
        const unavailable = {
          status: 'error',
          error: desktopBackendConfigurationCopy,
        } as const;
        setReadOutcomes({
          conversations: unavailable,
          memories: unavailable,
          tasks: unavailable,
        });
        setReadsPhase('unavailable');
        return;
      }
      const seq = ++refreshSeqRef.current;
      setReadsPhase(
        initial && readOutcomesRef.current === null
          ? 'initial-loading'
          : 'refreshing',
      );
      try {
        const outcomes = await loadDesktopReads(backend);
        // A newer refresh or a gate transition retired this one: its rows
        // belong to a session that is no longer mounted.
        if (seq !== refreshSeqRef.current) {
          return;
        }
        const previous = readOutcomesRef.current;
        const hadSavedRows =
          previous !== null &&
          [previous.conversations, previous.memories].some(
            outcome =>
              outcome.status === 'success' && outcome.value.items.length > 0,
          );
        const homeOutcomes = [outcomes.conversations, outcomes.memories];
        const failed = homeOutcomes.some(outcome => outcome.status === 'error');
        setReadOutcomes(current => {
          let next: DesktopReadOutcomes;
          if (current === null) {
            next = outcomes;
          } else {
            next = {
              conversations:
                outcomes.conversations.status === 'success'
                  ? outcomes.conversations
                  : current.conversations,
              memories:
                outcomes.memories.status === 'success'
                  ? outcomes.memories
                  : current.memories,
              tasks:
                outcomes.tasks.status === 'success'
                  ? outcomes.tasks
                  : current.tasks,
            };
          }
          readOutcomesRef.current = next;
          if (
            next.conversations.status === 'success' ||
            next.memories.status === 'success'
          ) {
            homeReadsLoadedRef.current = true;
          }
          return next;
        });
        const hasSavedRows = homeOutcomes.some(
          outcome =>
            outcome.status === 'success' && outcome.value.items.length > 0,
        );
        setReadsPhase(
          failed
            ? hasSavedRows || hadSavedRows
              ? 'saved-but-refresh-failed'
              : 'unavailable'
            : 'ready',
        );
      } catch {
        if (seq !== refreshSeqRef.current) {
          return;
        }
        setReadsPhase(
          readOutcomesRef.current === null
            ? 'unavailable'
            : 'saved-but-refresh-failed',
        );
      }
    },
    [enabled],
  );

  useEffect(() => {
    if (!enabled) {
      // Leaving the ready session drops every saved row and phase so the
      // next session starts at a truthful initial-loading, never a stale
      // unavailable banner. Bumping the sequence also retires any refresh
      // still in flight from the session that just left, so its late rows
      // cannot seed the next session's "saved data" merge source.
      refreshSeqRef.current += 1;
      readOutcomesRef.current = null;
      homeReadsLoadedRef.current = false;
      setReadOutcomes(null);
      setReadsPhase('initial-loading');
      return;
    }
    refreshReads(true).catch(() => undefined);
  }, [enabled, refreshReads]);

  const reads = useMemo(() => {
    if (readOutcomes === null) {
      return [];
    }
    return [
      ...(readOutcomes.conversations.status === 'success'
        ? readOutcomes.conversations.value.items
        : []),
      ...(readOutcomes.memories.status === 'success'
        ? readOutcomes.memories.value.items
        : []),
    ].sort(
      (left, right) =>
        (projectionTimestamp(right) ?? 0) - (projectionTimestamp(left) ?? 0),
    );
  }, [readOutcomes]);

  const allHomeReadsUnavailable =
    readOutcomes !== null &&
    readOutcomes.conversations.status === 'error' &&
    readOutcomes.memories.status === 'error';

  return {
    allHomeReadsUnavailable,
    homeReadsLoadedRef,
    readOutcomes,
    reads,
    readsPhase,
    refreshReads,
  };
}
