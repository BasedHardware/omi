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

export type PreparedTaskPatch = Readonly<{
  recordId: string;
  writeId: string;
  body: string;
}>;

export type TaskPatchResult =
  | {ok: true; revision: string}
  | {ok: false; failure: WriteFailure; controlUnavailable: boolean};

export async function prepareTaskPatch(
  backend: OmiBackend,
  input: {
    recordId: string;
    baseRevision: string;
    accountEpoch: number;
    patch: {completed?: boolean; description?: string};
  },
): Promise<PreparedTaskPatch> {
  const keys = Object.keys(input.patch);
  if (
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
      path: '/v1/tasks/ops',
      body: prepared.body,
    });
  } catch {
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
