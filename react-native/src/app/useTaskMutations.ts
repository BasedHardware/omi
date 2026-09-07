import {useCallback, useEffect, useRef, useState} from 'react';
import type {TaskRead, TaskReadOutcome} from '../desktopReadClient';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from '../omiNative';
import {
  prepareTaskPatch,
  sendTaskPatch,
  TASK_WRITE_UNAVAILABLE_DETAIL,
  type PreparedTaskPatch,
} from '../taskMutationClient';

export function useTaskMutations({
  enabled,
  outcome,
  refreshTasks,
  revalidateSession,
}: {
  enabled: boolean;
  outcome: TaskReadOutcome | null;
  refreshTasks: () => Promise<TaskRead | null>;
  revalidateSession: () => Promise<void>;
}) {
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const pending = useRef<PreparedTaskPatch | null>(null);
  const active = useRef(false);
  const generation = useRef(0);
  const retryAfter = useRef(0);
  const acknowledged = useRef(false);
  const writesAvailable: boolean | null =
    outcome?.status !== 'success'
      ? null
      : enabled &&
        omiBackend != null &&
        (outcome.value.apiContract === 'omi' ||
          (omiBackend.createWriteId !== undefined &&
            Number.isSafeInteger(outcome.value.accountEpoch) &&
            outcome.value.accountEpoch !== null));

  const reset = useCallback(() => {
    ++generation.current;
    pending.current = null;
    active.current = false;
    acknowledged.current = false;
    retryAfter.current = 0;
    setBusyTaskId(null);
    setError(null);
    setCanRetry(false);
  }, []);

  useEffect(() => {
    if (!enabled) {
      reset();
    }
    return reset;
  }, [enabled, reset]);

  useEffect(() => subscribeOmiBackendSessionInvalidated(reset), [reset]);

  const submit = useCallback(
    async (prepared: PreparedTaskPatch, epoch: number) => {
      if (omiBackend == null || epoch !== generation.current) {
        return;
      }
      active.current = true;
      setCanRetry(false);
      setError(null);
      try {
        if (!acknowledged.current) {
          const result = await sendTaskPatch(omiBackend, prepared);
          if (epoch !== generation.current) {
            return;
          }
          if (!result.ok) {
            const failure = result.failure;
            if (failure.kind === 'auth-invalid') {
              setError('Sign in again before changing tasks.');
              await revalidateSession();
            } else if (failure.kind === 'permanent') {
              setError(
                failure.reason === 'conflict'
                  ? 'This task changed elsewhere. Review the latest task before editing again.'
                  : failure.reason === 'gone' &&
                    failure.detail === TASK_WRITE_UNAVAILABLE_DETAIL
                  ? 'Task editing is not available from this backend yet.'
                  : 'This change was not accepted. Your edit remains here to copy or dismiss.',
              );
              if (
                failure.reason === 'conflict' ||
                failure.reason === 'stale_epoch'
              ) {
                await refreshTasks();
              }
            } else {
              retryAfter.current =
                failure.kind === 'rate-limited'
                  ? Date.now() + failure.retryAfterMs
                  : 0;
              setError(
                result.controlUnavailable
                  ? 'Task editing is temporarily unavailable. Retry when the service is ready.'
                  : 'The change could not be confirmed. Retry to check the same change.',
              );
              setCanRetry(true);
            }
            return;
          }
          acknowledged.current = true;
        }
        const refreshed = await refreshTasks();
        if (epoch !== generation.current) {
          return;
        }
        if (
          refreshed === null ||
          refreshed.page.completenessStatus !== 'complete'
        ) {
          setError(
            'Saved, but the latest tasks could not be loaded. Retry to refresh.',
          );
          setCanRetry(true);
        } else {
          reset();
        }
      } catch {
        if (epoch === generation.current) {
          setError(
            'The change could not be confirmed. Retry to check the same change.',
          );
          setCanRetry(true);
        }
      } finally {
        if (epoch === generation.current) {
          active.current = false;
        }
      }
    },
    [refreshTasks, reset, revalidateSession],
  );

  const change = useCallback(
    async (id: string, patch: {completed?: boolean; description?: string}) => {
      if (
        !writesAvailable ||
        active.current ||
        pending.current !== null ||
        omiBackend == null ||
        outcome?.status !== 'success'
      ) {
        return;
      }
      const task = outcome.value.items.find(item => item.id === id);
      if (
        task === undefined ||
        (outcome.value.apiContract !== 'omi' &&
          (task.revision == null || outcome.value.accountEpoch == null))
      ) {
        setError('Refresh this task before editing.');
        return;
      }
      const epoch = generation.current;
      active.current = true;
      setBusyTaskId(id);
      setError(null);
      try {
        const prepared = await prepareTaskPatch(omiBackend, {
          ...(outcome.value.apiContract === 'omi'
            ? {apiContract: 'omi' as const}
            : {}),
          recordId: id,
          baseRevision: task.revision,
          accountEpoch: outcome.value.accountEpoch,
          patch,
        });
        if (epoch !== generation.current) {
          return;
        }
        // ponytail: pending edits live in memory; account-bound native journaling is required for process-death recovery.
        pending.current = prepared;
        await submit(prepared, epoch);
      } catch {
        if (epoch === generation.current) {
          setError(
            'The change could not be prepared. Your edit has not been sent.',
          );
          setBusyTaskId(null);
        }
      } finally {
        if (epoch === generation.current) {
          active.current = false;
        }
      }
    },
    [outcome, submit, writesAvailable],
  );

  const retry = useCallback(async () => {
    if (!enabled || active.current || !canRetry || pending.current === null) {
      return;
    }
    if (Date.now() < retryAfter.current) {
      setError('Please wait before retrying this change.');
      return;
    }
    await submit(pending.current, generation.current);
  }, [canRetry, enabled, submit]);

  return {
    writesAvailable,
    busyTaskId,
    taskMutationError: error,
    onTaskToggle: (id: string) => {
      const task =
        outcome?.status === 'success'
          ? outcome.value.items.find(item => item.id === id)
          : undefined;
      if (task !== undefined) {
        change(id, {completed: !task.completed}).catch(() => undefined);
      }
    },
    onTaskEdit: (id: string, description: string) => {
      change(id, {description}).catch(() => undefined);
    },
    onRetryTaskMutation: canRetry
      ? () => {
          retry().catch(() => undefined);
        }
      : undefined,
    onDismissTaskMutation: error !== null ? reset : undefined,
  };
}
