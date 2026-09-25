import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  loadDesktopReads,
  loadTasks,
  loadConversations,
  ConversationCursorExpiredError,
  TaskCursorExpiredError,
  type TaskRead,
  projectionTimestamp,
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopLocalBackendServiceCopy,
  type DomainReadOutcome,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
} from '../desktopReadClient';
import {omiBackend, type OmiBackend} from '../omiNative';

export type ProjectionFilter = 'all' | DesktopReadProjection['kind'];
export type ReadsPhase =
  | 'initial-loading'
  | 'refreshing'
  | 'ready'
  | 'saved-but-refresh-failed'
  | 'unavailable';

async function revalidateLoadedWindow<
  T extends {
    items: Array<{id: string}>;
    page: {hasMore: boolean; nextCursor: string | null};
  },
>(
  load: (cursor: string | null) => Promise<T>,
  previousCount: number,
  stillCurrent: () => boolean,
): Promise<T | null> {
  const items: T['items'] = [];
  const ids = new Set<string>();
  let cursor: string | null = null;
  let latest!: T;
  while (items.length < 10000) {
    if (!stillCurrent()) {
      return null;
    }
    latest = await load(cursor);
    if (!stillCurrent()) {
      return null;
    }
    for (const item of latest.items) {
      if (ids.has(item.id)) {
        throw new Error('Loaded page did not advance');
      }
      ids.add(item.id);
      items.push(item);
    }
    cursor = latest.page.nextCursor;
    if (
      items.length >= previousCount ||
      !latest.page.hasMore ||
      cursor === null
    ) {
      break;
    }
  }
  return stillCurrent() ? {...latest, items} : null;
}

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

type PagedRead = {
  items: Array<{id: string}>;
  page: {hasMore: boolean; nextCursor: string | null};
};

// Everything loadMoreConversations and loadMoreTasks share: the guard
// cluster, sequence capture, cursor-expired recovery, 10k cap, id-dedupe /
// page-advance checks, merge, extended bookkeeping, and finally fences. The
// tasks-only accountEpoch guard rides in validateAppend.
type LoadMoreSpec<TRead extends PagedRead> = {
  pendingRef: {current: boolean};
  setLoadingMore: (loading: boolean) => void;
  setNotice: (notice: string | null) => void;
  outcome: (
    outcomes: DesktopReadOutcomes,
  ) => {status: 'success'; value: TRead} | {status: 'error'; error: string};
  load: (backend: OmiBackend, cursor?: string | null) => Promise<TRead>;
  cursorExpired: (error: unknown) => boolean;
  validateAppend?: (next: TRead, current: TRead) => void;
  listTooLargeMessage: string;
  pageDidNotAdvanceMessage: string;
  refreshNotice: string;
  failureNotice: string;
  merge: (current: DesktopReadOutcomes, value: TRead) => DesktopReadOutcomes;
  extendedRef: {current: boolean};
  setExtended: (extended: boolean) => void;
};

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
  const conversationPagePendingRef = useRef(false);
  const taskPagePendingRef = useRef(false);
  const [tasksLoadingMore, setTasksLoadingMore] = useState(false);
  const [taskNotice, setTaskNotice] = useState<string | null>(null);
  const refreshPendingRef = useRef(false);
  const conversationsExtendedRef = useRef(false);
  const tasksExtendedRef = useRef(false);
  const [conversationsExtended, setConversationsExtended] = useState(false);
  const [, setTasksExtended] = useState(false);
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
    taskPagePendingRef.current = false;
    setTasksLoadingMore(false);
    setTaskNotice(null);
    setConversationsLoadingMore(false);
    setConversationNotice(null);
    readOutcomesRef.current = null;
    homeReadsLoadedRef.current = false;
    setReadOutcomes(null);
    conversationsExtendedRef.current = false;
    tasksExtendedRef.current = false;
    setConversationsExtended(false);
    setTasksExtended(false);
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
        // Mirror every other outcome writer: retire any in-flight refresh and
        // keep the ref in sync so pagination/merge sources never read stale
        // rows from a session whose credentials disappeared.
        refreshSeqRef.current += 1;
        refreshPendingRef.current = false;
        conversationPagePendingRef.current = false;
        taskPagePendingRef.current = false;
        const unavailable = {
          status: 'error',
          error: desktopBackendConfigurationCopy,
        } as const;
        const next: DesktopReadOutcomes = {
          conversations: unavailable,
          memories: unavailable,
          tasks: unavailable,
        };
        readOutcomesRef.current = next;
        setReadOutcomes(next);
        setReadsPhase('unavailable');
        return;
      }
      const seq = ++refreshSeqRef.current;
      const stillCurrent = () => seq === refreshSeqRef.current;
      conversationPagePendingRef.current = false;
      taskPagePendingRef.current = false;
      setTasksLoadingMore(false);
      setTaskNotice(null);
      setConversationsLoadingMore(false);
      setConversationNotice(null);
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
        if (!stillCurrent()) {
          return;
        }
        const previous = readOutcomesRef.current;
        if (
          conversationsExtendedRef.current &&
          previous?.conversations.status === 'success' &&
          outcomes.conversations.status === 'success'
        ) {
          const conversations = await revalidateLoadedWindow(
            loadCursor => loadConversations(backend, loadCursor),
            previous.conversations.value.items.length,
            stillCurrent,
          );
          if (conversations === null) {
            return;
          }
          outcomes.conversations = {status: 'success', value: conversations};
        }
        if (!stillCurrent()) {
          return;
        }
        if (
          tasksExtendedRef.current &&
          previous?.tasks.status === 'success' &&
          outcomes.tasks.status === 'success'
        ) {
          const tasks = await revalidateLoadedWindow(
            loadCursor => loadTasks(backend, loadCursor),
            previous.tasks.value.items.length,
            stillCurrent,
          );
          if (tasks === null) {
            return;
          }
          outcomes.tasks = {status: 'success', value: tasks};
        }
        if (!stillCurrent()) {
          return;
        }
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

  const loadMore = useCallback(
    async <TRead extends PagedRead>(
      spec: LoadMoreSpec<TRead>,
    ): Promise<void> => {
      const previous = readOutcomesRef.current;
      const previousOutcome = previous === null ? null : spec.outcome(previous);
      if (
        !enabled ||
        omiBackend == null ||
        spec.pendingRef.current ||
        refreshPendingRef.current ||
        previousOutcome?.status !== 'success' ||
        !previousOutcome.value.page.hasMore ||
        previousOutcome.value.page.nextCursor === null
      ) {
        return;
      }
      const backend = omiBackend;
      const cursor = previousOutcome.value.page.nextCursor;
      const sequence = refreshSeqRef.current;
      spec.pendingRef.current = true;
      spec.setLoadingMore(true);
      spec.setNotice(null);
      try {
        let replace = false;
        let next: TRead;
        try {
          next = await spec.load(backend, cursor);
        } catch (error) {
          if (
            !spec.cursorExpired(error) ||
            sequence !== refreshSeqRef.current
          ) {
            throw error;
          }
          replace = true;
          next = await spec.load(backend);
        }
        if (sequence !== refreshSeqRef.current) {
          return;
        }
        const current = readOutcomesRef.current;
        if (current === null) {
          return;
        }
        const currentOutcome = spec.outcome(current);
        if (currentOutcome.status !== 'success') {
          return;
        }
        if (!replace) {
          spec.validateAppend?.(next, currentOutcome.value);
        }
        const items = replace
          ? next.items
          : [...currentOutcome.value.items, ...next.items];
        if (items.length > 10000) {
          throw new Error(spec.listTooLargeMessage);
        }
        if (
          new Set(items.map(item => item.id)).size !== items.length ||
          (!replace && next.page.hasMore && next.page.nextCursor === cursor)
        ) {
          throw new Error(spec.pageDidNotAdvanceMessage);
        }
        const merged = spec.merge(current, {...next, items});
        readOutcomesRef.current = merged;
        setReadOutcomes(merged);
        spec.extendedRef.current = !replace && items.length > next.items.length;
        spec.setExtended(spec.extendedRef.current);
        if (replace) {
          spec.setNotice(spec.refreshNotice);
        }
      } catch {
        if (sequence === refreshSeqRef.current) {
          spec.setNotice(spec.failureNotice);
        }
      } finally {
        if (sequence === refreshSeqRef.current) {
          spec.pendingRef.current = false;
          spec.setLoadingMore(false);
        }
      }
    },
    [enabled],
  );

  const loadMoreConversations = useCallback(
    () =>
      loadMore({
        pendingRef: conversationPagePendingRef,
        setLoadingMore: setConversationsLoadingMore,
        setNotice: setConversationNotice,
        outcome: outcomes => outcomes.conversations,
        load: loadConversations,
        cursorExpired: error => error instanceof ConversationCursorExpiredError,
        listTooLargeMessage: 'Conversation list is too large',
        pageDidNotAdvanceMessage: 'Conversation page did not advance',
        refreshNotice: 'Conversations changed. The list has been refreshed.',
        failureNotice: 'More conversations could not be loaded. Try again.',
        merge: (current, value) => ({
          ...current,
          conversations: {status: 'success' as const, value},
        }),
        extendedRef: conversationsExtendedRef,
        setExtended: setConversationsExtended,
      }),
    [loadMore],
  );

  const loadMoreTasks = useCallback(
    () =>
      loadMore({
        pendingRef: taskPagePendingRef,
        setLoadingMore: setTasksLoadingMore,
        setNotice: setTaskNotice,
        outcome: outcomes => outcomes.tasks,
        load: loadTasks,
        cursorExpired: error => error instanceof TaskCursorExpiredError,
        // Tasks carry an account epoch: an appended page from a different
        // epoch must never merge into the visible list.
        validateAppend: (next, current) => {
          if (next.accountEpoch !== current.accountEpoch) {
            throw new Error('Task account epoch changed');
          }
        },
        listTooLargeMessage: 'Task list is too large',
        pageDidNotAdvanceMessage: 'Task page did not advance',
        refreshNotice: 'Tasks changed. The list has been refreshed.',
        failureNotice: 'More tasks could not be loaded. Try again.',
        merge: (current, value) => ({
          ...current,
          tasks: {status: 'success' as const, value},
        }),
        extendedRef: tasksExtendedRef,
        setExtended: setTasksExtended,
      }),
    [loadMore],
  );

  const refreshTasks = useCallback(async (): Promise<TaskRead | null> => {
    if (!enabled || omiBackend == null) {
      return null;
    }
    const backend = omiBackend;
    const sequence = ++refreshSeqRef.current;
    const stillCurrent = () => sequence === refreshSeqRef.current;
    conversationPagePendingRef.current = false;
    taskPagePendingRef.current = false;
    setTasksLoadingMore(false);
    setTaskNotice(null);
    refreshPendingRef.current = true;
    setConversationsLoadingMore(false);
    try {
      const tasks = await loadTasks(backend);
      const previous = readOutcomesRef.current;
      if (!stillCurrent() || previous === null) {
        return null;
      }
      const previousTasks =
        previous.tasks.status === 'success' ? previous.tasks.value : null;
      const mergedTasks =
        tasksExtendedRef.current && previousTasks !== null
          ? await revalidateLoadedWindow(
              loadCursor => loadTasks(backend, loadCursor),
              previousTasks.items.length,
              stillCurrent,
            )
          : tasks;
      if (mergedTasks === null || !stillCurrent()) {
        return null;
      }
      const next: DesktopReadOutcomes = {
        ...previous,
        tasks: {status: 'success', value: mergedTasks},
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
      if (stillCurrent()) refreshPendingRef.current = false;
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
    conversationsLoadingMore,
    conversationsExtended,
    conversationNotice,
    loadMoreConversations,
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
