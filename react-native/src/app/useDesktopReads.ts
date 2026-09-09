import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  loadDesktopReads,
  loadTasks,
  loadConversations,
  loadMemories,
  ConversationCursorExpiredError,
  MemoryCursorExpiredError,
  TaskCursorExpiredError,
  type TaskRead,
  projectionTimestamp,
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopLocalBackendServiceCopy,
  desktopBackendUnavailableCopy,
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

function mergeOutcome<T extends DomainReadOutcome<DesktopReadProjection>>(
  current: T,
  next: T,
): T {
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
  const [conversationsLoadingMore, setConversationsLoadingMore] =
    useState(false);
  const [conversationNotice, setConversationNotice] = useState<string | null>(
    null,
  );
  const [conversationsPageRetryable, setConversationsPageRetryable] =
    useState(true);
  const conversationPagePendingRef = useRef(false);
  const memoryPagePendingRef = useRef(false);
  const [memoriesLoadingMore, setMemoriesLoadingMore] = useState(false);
  const [memoryNotice, setMemoryNotice] = useState<string | null>(null);
  const [memoriesPageRetryable, setMemoriesPageRetryable] = useState(true);
  const taskPagePendingRef = useRef(false);
  const [tasksLoadingMore, setTasksLoadingMore] = useState(false);
  const [taskNotice, setTaskNotice] = useState<string | null>(null);
  const [tasksPageRetryable, setTasksPageRetryable] = useState(true);
  const refreshPendingRef = useRef(false);
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
    refreshPendingRef.current = false;
    conversationPagePendingRef.current = false;
    memoryPagePendingRef.current = false;
    taskPagePendingRef.current = false;
    setTasksLoadingMore(false);
    setTaskNotice(null);
    setTasksPageRetryable(true);
    setConversationsLoadingMore(false);
    setConversationNotice(null);
    setConversationsPageRetryable(true);
    setMemoriesLoadingMore(false);
    setMemoryNotice(null);
    setMemoriesPageRetryable(true);
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
      conversationPagePendingRef.current = false;
      memoryPagePendingRef.current = false;
      taskPagePendingRef.current = false;
      setTasksLoadingMore(false);
      setTaskNotice(null);
      setConversationsLoadingMore(false);
      setConversationNotice(null);
      setConversationsPageRetryable(true);
      setMemoriesLoadingMore(false);
      setMemoryNotice(null);
      setMemoriesPageRetryable(true);
      setTasksPageRetryable(true);
      refreshPendingRef.current = true;
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
      } finally {
        if (seq === refreshSeqRef.current) {
          refreshPendingRef.current = false;
        }
      }
    },
    [enabled],
  );

  const loadMoreConversations = useCallback(async () => {
    const previous = readOutcomesRef.current;
    if (
      !enabled ||
      omiBackend == null ||
      conversationPagePendingRef.current ||
      refreshPendingRef.current ||
      previous?.conversations.status !== 'success' ||
      !previous.conversations.value.page.hasMore ||
      previous.conversations.value.page.nextCursor === null
    ) {
      return;
    }
    const cursor = previous.conversations.value.page.nextCursor;
    const sequence = refreshSeqRef.current;
    conversationPagePendingRef.current = true;
    setConversationsLoadingMore(true);
    setConversationNotice(null);
    try {
      let replace = false;
      let next;
      try {
        next = await loadConversations(omiBackend, cursor);
      } catch (error) {
        if (
          !(error instanceof ConversationCursorExpiredError) ||
          sequence !== refreshSeqRef.current
        ) {
          throw error;
        }
        replace = true;
        next = await loadConversations(omiBackend);
      }
      if (sequence !== refreshSeqRef.current) {
        return;
      }
      const current = readOutcomesRef.current;
      if (current === null || current.conversations.status !== 'success') {
        return;
      }
      const items = replace
        ? next.items
        : [...current.conversations.value.items, ...next.items];
      if (items.length > 10000) {
        throw new Error('Conversation list is too large');
      }
      if (
        new Set(items.map(item => item.id)).size !== items.length ||
        (!replace && next.page.hasMore && next.page.nextCursor === cursor)
      ) {
        throw new Error('Conversation page did not advance');
      }
      const merged = {
        ...current,
        conversations: {status: 'success' as const, value: {...next, items}},
      };
      readOutcomesRef.current = merged;
      setReadOutcomes(merged);
      if (replace) {
        setConversationNotice(
          'Conversations changed. The list has been refreshed.',
        );
      }
      setConversationsPageRetryable(true);
    } catch (error) {
      if (sequence === refreshSeqRef.current) {
        const unavailable =
          error instanceof Error &&
          error.message === desktopBackendUnavailableCopy;
        setConversationsPageRetryable(!unavailable);
        setConversationNotice(
          unavailable
            ? desktopBackendUnavailableCopy
            : 'More conversations could not be loaded. Try again.',
        );
      }
    } finally {
      if (sequence === refreshSeqRef.current) {
        conversationPagePendingRef.current = false;
        setConversationsLoadingMore(false);
      }
    }
  }, [enabled]);

  const loadMoreMemories = useCallback(async () => {
    const previous = readOutcomesRef.current;
    if (
      !enabled ||
      omiBackend == null ||
      memoryPagePendingRef.current ||
      refreshPendingRef.current ||
      previous?.memories.status !== 'success' ||
      !previous.memories.value.page.hasMore ||
      previous.memories.value.page.nextCursor === null
    ) {
      return;
    }
    const cursor = previous.memories.value.page.nextCursor;
    const sequence = refreshSeqRef.current;
    memoryPagePendingRef.current = true;
    setMemoriesLoadingMore(true);
    setMemoryNotice(null);
    try {
      let replace = false;
      let next;
      try {
        next = await loadMemories(omiBackend, cursor);
      } catch (error) {
        if (
          !(error instanceof MemoryCursorExpiredError) ||
          sequence !== refreshSeqRef.current
        ) {
          throw error;
        }
        replace = true;
        next = await loadMemories(omiBackend);
      }
      if (sequence !== refreshSeqRef.current) {
        return;
      }
      const current = readOutcomesRef.current;
      if (current === null || current.memories.status !== 'success') {
        return;
      }
      const items = replace
        ? next.items
        : [...current.memories.value.items, ...next.items];
      if (items.length > 10000) {
        throw new Error('Memory list is too large');
      }
      if (
        new Set(items.map(item => item.id)).size !== items.length ||
        (!replace && next.page.hasMore && next.page.nextCursor === cursor)
      ) {
        throw new Error('Memory page did not advance');
      }
      const merged = {
        ...current,
        memories: {status: 'success' as const, value: {...next, items}},
      };
      readOutcomesRef.current = merged;
      setReadOutcomes(merged);
      if (replace) {
        setMemoryNotice('Memories changed. The list has been refreshed.');
      }
      setMemoriesPageRetryable(true);
    } catch (error) {
      if (sequence === refreshSeqRef.current) {
        const unavailable =
          error instanceof Error &&
          error.message === desktopBackendUnavailableCopy;
        setMemoriesPageRetryable(!unavailable);
        setMemoryNotice(
          unavailable
            ? desktopBackendUnavailableCopy
            : 'More memories could not be loaded.',
        );
      }
    } finally {
      if (sequence === refreshSeqRef.current) {
        memoryPagePendingRef.current = false;
        setMemoriesLoadingMore(false);
      }
    }
  }, [enabled]);

  const loadMoreTasks = useCallback(async () => {
    const previous = readOutcomesRef.current;
    if (
      !enabled ||
      omiBackend == null ||
      taskPagePendingRef.current ||
      refreshPendingRef.current ||
      previous?.tasks.status !== 'success' ||
      !previous.tasks.value.page.hasMore ||
      previous.tasks.value.page.nextCursor === null
    ) {
      return;
    }
    const cursor = previous.tasks.value.page.nextCursor;
    const sequence = refreshSeqRef.current;
    taskPagePendingRef.current = true;
    setTasksLoadingMore(true);
    setTaskNotice(null);
    try {
      let replace = false;
      let next;
      try {
        next = await loadTasks(omiBackend, cursor);
      } catch (error) {
        if (
          !(error instanceof TaskCursorExpiredError) ||
          sequence !== refreshSeqRef.current
        ) {
          throw error;
        }
        replace = true;
        next = await loadTasks(omiBackend);
      }
      if (sequence !== refreshSeqRef.current) {
        return;
      }
      const current = readOutcomesRef.current;
      if (current === null || current.tasks.status !== 'success') {
        return;
      }
      if (!replace && next.accountEpoch !== current.tasks.value.accountEpoch)
        throw new Error('Task account epoch changed');
      const items = replace
        ? next.items
        : [...current.tasks.value.items, ...next.items];
      if (items.length > 10000) {
        throw new Error('Task list is too large');
      }
      if (
        new Set(items.map(item => item.id)).size !== items.length ||
        (!replace && next.page.hasMore && next.page.nextCursor === cursor)
      ) {
        throw new Error('Task page did not advance');
      }
      const merged = {
        ...current,
        tasks: {status: 'success' as const, value: {...next, items}},
      };
      readOutcomesRef.current = merged;
      setReadOutcomes(merged);
      if (replace) {
        setTaskNotice('Tasks changed. The list has been refreshed.');
      }
      setTasksPageRetryable(true);
    } catch (error) {
      if (sequence === refreshSeqRef.current) {
        const unavailable =
          error instanceof Error &&
          error.message === desktopBackendUnavailableCopy;
        setTasksPageRetryable(!unavailable);
        setTaskNotice(
          unavailable
            ? desktopBackendUnavailableCopy
            : 'More tasks could not be loaded. Try again.',
        );
      }
    } finally {
      if (sequence === refreshSeqRef.current) {
        taskPagePendingRef.current = false;
        setTasksLoadingMore(false);
      }
    }
  }, [enabled]);

  const refreshTasks = useCallback(async (): Promise<TaskRead | null> => {
    if (!enabled || omiBackend == null) {
      return null;
    }
    const sequence = ++refreshSeqRef.current;
    conversationPagePendingRef.current = false;
    memoryPagePendingRef.current = false;
    taskPagePendingRef.current = false;
    setTasksLoadingMore(false);
    setTaskNotice(null);
    setTasksPageRetryable(true);
    refreshPendingRef.current = true;
    setConversationsLoadingMore(false);
    setMemoriesLoadingMore(false);
    try {
      const tasks = await loadTasks(omiBackend);
      const previous = readOutcomesRef.current;
      if (sequence !== refreshSeqRef.current || previous === null) {
        return null;
      }
      const next: DesktopReadOutcomes = {
        ...previous,
        tasks: {status: 'success', value: tasks},
      };
      readOutcomesRef.current = next;
      setReadOutcomes(next);
      setReadsPhase(
        [next.conversations, next.memories].some(
          value => value.status === 'error',
        )
          ? 'saved-but-refresh-failed'
          : 'ready',
      );
      return tasks;
    } catch {
      return null;
    } finally {
      if (sequence === refreshSeqRef.current) refreshPendingRef.current = false;
    }
  }, [enabled]);

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

  useEffect(
    () => () => {
      refreshSeqRef.current += 1;
      conversationPagePendingRef.current = false;
      taskPagePendingRef.current = false;
      refreshPendingRef.current = false;
    },
    [],
  );

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
    tasksLoadingMore,
    taskNotice,
    loadMoreTasks,
    tasksPageRetryable,
    conversationsLoadingMore,
    conversationNotice,
    loadMoreConversations,
    conversationsPageRetryable,
    memoriesLoadingMore,
    memoryNotice,
    loadMoreMemories,
    memoriesPageRetryable,
    allHomeReadsUnavailable,
    homeReadsLoadedRef,
    readOutcomes,
    reads,
    readsPhase,
    resetReads,
    refreshReads,
    refreshTasks,
  };
}
