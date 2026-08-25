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

export function useDesktopReads() {
  const [readOutcomes, setReadOutcomes] = useState<DesktopReadOutcomes | null>(
    null,
  );
  const readOutcomesRef = useRef<DesktopReadOutcomes | null>(null);
  // Tracks whether Home ever presented saved rows, independent of the latest
  // refresh outcome, so a failed first load followed by a retry stays truthful.
  const homeReadsLoadedRef = useRef(false);
  const [readsPhase, setReadsPhase] = useState<ReadsPhase>('initial-loading');

  const refreshReads = useCallback(async (initial: boolean) => {
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
    setReadsPhase(
      initial && readOutcomesRef.current === null
        ? 'initial-loading'
        : 'refreshing',
    );
    try {
      const outcomes = await loadDesktopReads(backend);
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
      setReadsPhase(
        readOutcomesRef.current === null
          ? 'unavailable'
          : 'saved-but-refresh-failed',
      );
    }
  }, []);

  useEffect(() => {
    refreshReads(true).catch(() => undefined);
  }, [refreshReads]);

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
