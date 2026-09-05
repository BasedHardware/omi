import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  loadDesktopReads,
  projectionTimestamp,
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopLocalBackendServiceCopy,
  type DomainReadOutcome,
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

function mergeOutcome<T extends DesktopReadProjection>(
  current: DomainReadOutcome<T>,
  next: DomainReadOutcome<T>,
): DomainReadOutcome<T> {
  const transientFailure =
    next.status === 'error' &&
    (next.error === desktopBackendServiceCopy ||
      next.error === desktopLocalBackendServiceCopy);
  return current.status === 'success' &&
    current.value.items.length > 0 &&
    transientFailure
    ? current
    : next;
}

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
  // signInAndRefresh flips the session gate then awaits refreshReads in the
  // same turn, before React re-renders with enabled===true. ignoreEnabled
  // makes that await load instead of no-op; this ref stops the enablement
  // effect from starting a second refresh that would retire the awaited one.
  const suppressEnableEffectLoadRef = useRef(false);

  const resetReads = useCallback(() => {
    refreshSeqRef.current += 1;
    readOutcomesRef.current = null;
    homeReadsLoadedRef.current = false;
    setReadOutcomes(null);
    setReadsPhase('initial-loading');
  }, []);

  // Cloud reads only run for a ready session. Signed-out and probing Macs
  // never hit /v1/conversations|memories|tasks, so their 401/unconfigured
  // failures cannot poison readsPhase for the session that signs in next.
  const refreshReads = useCallback(
    async (
      initial: boolean,
      options?: {
        // Post-sign-in: parent just flipped onboardingRequired, but this hook
        // still sees enabled===false until the next render. Allow one explicit
        // load so await refreshReads() is truthful instead of a no-op.
        ignoreEnabled?: boolean;
      },
    ) => {
      if (!enabled && options?.ignoreEnabled !== true) {
        return;
      }
      if (options?.ignoreEnabled === true && !enabled) {
        suppressEnableEffectLoadRef.current = true;
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
        const homeOutcomes = [
          outcomes.conversations,
          outcomes.memories,
          outcomes.tasks,
        ];
        const failed = homeOutcomes.some(outcome => outcome.status === 'error');
        // Merge first, then judge the phase from what the shell will actually
        // show. A non-transient failure replaces prior success rows; claiming
        // "showing saved data" after those rows are gone is a lie. Transient
        // service failures keep prior rows via mergeOutcome, so the merged
        // snapshot is the single source of truth for both paths.
        const next: DesktopReadOutcomes =
          previous === null
            ? outcomes
            : {
                conversations: mergeOutcome(
                  previous.conversations,
                  outcomes.conversations,
                ),
                memories: mergeOutcome(previous.memories, outcomes.memories),
                tasks: mergeOutcome(previous.tasks, outcomes.tasks),
              };
        readOutcomesRef.current = next;
        if (
          next.conversations.status === 'success' ||
          next.memories.status === 'success' ||
          next.tasks.status === 'success'
        ) {
          homeReadsLoadedRef.current = true;
        }
        setReadOutcomes(next);
        const showingSavedRows = [
          next.conversations,
          next.memories,
          next.tasks,
        ].some(
          outcome =>
            outcome.status === 'success' && outcome.value.items.length > 0,
        );
        setReadsPhase(
          failed
            ? showingSavedRows
              ? 'saved-but-refresh-failed'
              : 'unavailable'
            : 'ready',
        );
      } catch {
        if (seq !== refreshSeqRef.current) {
          return;
        }
        const retained = readOutcomesRef.current;
        const showingSavedRows =
          retained !== null &&
          [retained.conversations, retained.memories, retained.tasks].some(
            outcome =>
              outcome.status === 'success' && outcome.value.items.length > 0,
          );
        setReadsPhase(
          showingSavedRows ? 'saved-but-refresh-failed' : 'unavailable',
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
      suppressEnableEffectLoadRef.current = false;
      resetReads();
      return;
    }
    if (suppressEnableEffectLoadRef.current) {
      suppressEnableEffectLoadRef.current = false;
      return;
    }
    refreshReads(true).catch(() => undefined);
  }, [enabled, refreshReads, resetReads]);

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
    ].sort((left, right) => {
      const leftTs = projectionTimestamp(left);
      const rightTs = projectionTimestamp(right);
      return (
        (rightTs ?? Number.NEGATIVE_INFINITY) -
        (leftTs ?? Number.NEGATIVE_INFINITY)
      );
    });
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
    resetReads,
    refreshReads,
  };
}
