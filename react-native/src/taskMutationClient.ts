import {
  buildWriteOpEnvelope,
  classifyWriteOpsResponse,
  isControlUnavailable,
} from '@omi-core/adapters-platform';
import type {WriteFailure} from '@omi-core/contracts';
import {
  isTrustedWriteAccepted,
  isTrustedWriteOpEnvelope,
} from '@omi-core/ratified-contracts/write/ops';
import type {OmiBackend} from './omiNativeTypes';

export type PreparedTaskPatch =
  | Readonly<{
      apiContract?: 'canonical';
      recordId: string;
      writeId: string;
      body: string;
    }>
  | Readonly<{apiContract: 'omi'; recordId: string; body: string}>;

const attemptedOmiPatches = new WeakSet<PreparedTaskPatch>();

export type TaskPatchResult =
  | {ok: true; revision: string | null}
  | {ok: false; failure: WriteFailure; controlUnavailable: boolean};

export async function prepareTaskPatch(
  backend: OmiBackend,
  input: {
    recordId: string;
    apiContract?: 'omi';
    baseRevision: string | null;
    accountEpoch: number | null;
    patch: {completed?: boolean; description?: string};
  },
): Promise<PreparedTaskPatch> {
  const keys = Object.keys(input.patch);
  if (input.apiContract === 'omi') {
    if (
      !input.recordId ||
      input.recordId.length > 256 ||
      keys.length === 0 ||
      keys.some(key => key !== 'completed' && key !== 'description') ||
      ('completed' in input.patch &&
        typeof input.patch.completed !== 'boolean') ||
      ('description' in input.patch &&
        (typeof input.patch.description !== 'string' ||
          !input.patch.description.trim()))
    ) {
      throw new Error('Task edit is invalid');
    }
    const recordId = input.recordId;
    const body = JSON.stringify(input.patch);
    if ((await backend.getApiContract?.()) !== 'omi')
      throw new Error('Task backend changed');
    return Object.freeze({
      apiContract: 'omi',
      recordId,
      body,
    });
  }
  if (
    input.accountEpoch === null ||
    input.baseRevision === null ||
    !Number.isSafeInteger(input.accountEpoch) ||
    input.accountEpoch < 0 ||
    !/^[0-9a-f]{64}$/.test(input.baseRevision) ||
    keys.length === 0 ||
    keys.some(key => key !== 'completed' && key !== 'description') ||
    ('completed' in input.patch &&
      typeof input.patch.completed !== 'boolean') ||
    ('description' in input.patch &&
      (typeof input.patch.description !== 'string' ||
        input.patch.description.trim().length === 0))
  ) {
    throw new Error(
      'Task edit requires a current revision, account epoch and valid patch',
    );
  }
  const updatedAt = Date.now();
  const patch = {
    ...input.patch,
    updatedAt,
    ...('completed' in input.patch
      ? {completedAt: input.patch.completed ? updatedAt : null}
      : {}),
  };
  const recordId = input.recordId;
  const baseRevision = input.baseRevision;
  const accountEpoch = input.accountEpoch;
  if (backend.createWriteId === undefined) {
    throw new Error('Native write identity is unavailable');
  }
  const writeId = await backend.createWriteId();
  const built = buildWriteOpEnvelope(
    {
      domain: 'tasks',
      writeId,
      op: {
        op: 'patch',
        record_id: recordId,
        base_revision: baseRevision,
        patch,
      },
    },
    accountEpoch,
  );
  if (!built.ok || !isTrustedWriteOpEnvelope(built.envelope)) {
    throw new Error('Task edit identity or envelope is invalid');
  }
  return Object.freeze({
    recordId,
    writeId,
    body: JSON.stringify(built.envelope),
  });
}

export async function sendTaskPatch(
  backend: OmiBackend,
  prepared: PreparedTaskPatch,
): Promise<TaskPatchResult> {
  if (prepared.apiContract === 'omi')
    return sendOmiTaskPatch(backend, prepared);
  const retryable = (detail: string): TaskPatchResult => ({
    ok: false,
    failure: {kind: 'retryable', unclassified: true, detail},
    controlUnavailable: false,
  });
  let nativeResponse;
  try {
    nativeResponse = await backend.request({
      id: `task-write-${prepared.writeId}`,
      method: 'POST',
      expectedApiContract: 'canonical',
      path: '/v1/tasks/ops',
      body: prepared.body,
    });
  } catch (error) {
    if (backendChanged(error)) return taskConflict();
    return retryable('Task edit could not be confirmed by the transport');
  }
  let json: unknown = null;
  try {
    json = JSON.parse(nativeResponse.body ?? 'null');
  } catch {}
  if (nativeResponse.status === 200) {
    if (!isTrustedWriteAccepted(json) || json.applied.revision === null) {
      return retryable('Task edit acknowledgement could not be verified');
    }
    return {ok: true, revision: json.applied.revision};
  }
  const response = {
    status: nativeResponse.status,
    json,
    text: nativeResponse.body ?? '',
    ...(nativeResponse.retryAfterSeconds != null
      ? {retryAfterMs: nativeResponse.retryAfterSeconds * 1000}
      : {}),
  };
  const failure = classifyWriteOpsResponse(response, 'Task edit');
  return failure === null
    ? retryable('Task edit response could not be classified')
    : {
        ok: false,
        failure,
        controlUnavailable: isControlUnavailable(response),
      };
}

function backendChanged(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === 'object' &&
    'code' in error &&
    error.code === 'OMI_HTTP_BACKEND_CHANGED'
  );
}
function taskConflict(): TaskPatchResult {
  return {
    ok: false,
    failure: {
      kind: 'permanent',
      reason: 'conflict',
      detail: 'Review the current task before another edit',
    },
    controlUnavailable: false,
  };
}
async function sendOmiTaskPatch(
  backend: OmiBackend,
  prepared: Extract<PreparedTaskPatch, {apiContract: 'omi'}>,
): Promise<TaskPatchResult> {
  const unknown = (): TaskPatchResult => ({
    ok: false,
    failure: {
      kind: 'retryable',
      unclassified: true,
      detail:
        'Task edit is unconfirmed; check the saved task before any further edit',
    },
    controlUnavailable: false,
  });
  try {
    if ((await backend.getApiContract?.()) !== 'omi') return taskConflict();
    const reconcile = attemptedOmiPatches.has(prepared);
    attemptedOmiPatches.add(prepared);
    const response = await backend.request({
      id: `omi-task-${prepared.recordId}`,
      method: reconcile ? 'GET' : 'PATCH',
      expectedApiContract: 'omi',
      path: `/v1/action-items/${encodeURIComponent(prepared.recordId)}`,
      ...(reconcile ? {} : {body: prepared.body}),
    });
    if (response.status === 401)
      return {
        ok: false,
        failure: {kind: 'auth-invalid', detail: 'Sign in before editing tasks'},
        controlUnavailable: false,
      };
    if (response.status === 429) {
      const seconds = response.retryAfterSeconds;
      return {
        ok: false,
        failure: {
          kind: 'rate-limited',
          retryAfterMs:
            typeof seconds === 'number' &&
            Number.isFinite(seconds) &&
            seconds >= 0
              ? seconds * 1000
              : 1000,
          detail: 'Wait before checking the saved task',
        },
        controlUnavailable: false,
      };
    }
    if ([400, 403, 404, 409, 422].includes(response.status))
      return {
        ok: false,
        failure: {
          kind: 'permanent',
          reason:
            response.status === 409
              ? 'conflict'
              : response.status === 404
              ? 'gone'
              : 'validation',
          detail: 'The service did not accept this task edit',
        },
        controlUnavailable: false,
      };
    if (response.status !== 200) return unknown();
    let value: unknown;
    try {
      value = JSON.parse(response.body ?? 'null');
    } catch {
      return unknown();
    }
    if (value === null || typeof value !== 'object' || Array.isArray(value))
      return unknown();
    const item = value as Record<string, unknown>;
    const patch = JSON.parse(prepared.body) as Record<string, unknown>;
    if (
      item.id !== prepared.recordId ||
      typeof item.completed !== 'boolean' ||
      typeof item.description !== 'string'
    )
      return unknown();
    if (!Object.entries(patch).every(([key, desired]) => item[key] === desired))
      return reconcile ? taskConflict() : unknown();
    return {ok: true, revision: null};
  } catch (error) {
    return backendChanged(error) ? taskConflict() : unknown();
  }
}
