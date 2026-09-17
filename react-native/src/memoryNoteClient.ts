import {isTrustedWriteAccepted} from '@omi-core/ratified-contracts/write/ops';
import type {OmiBackend} from './omiNativeTypes';

/**
 * User-authored memory notes are the only memory write surface currently
 * exposed by the platform. Synthesized memories remain read-only; this client
 * deliberately targets the dedicated STM-note door instead of pretending that
 * /v1/memories/ops can edit a projection.
 */
export const STM_NOTES_OPS_PATH = '/v1/stm-notes/ops';

export class TimelineMemorySaveError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

export type SavedTimelineMemory = {
  id: string;
  idempotent: boolean;
};

function parseAccepted(body: string | null): SavedTimelineMemory {
  if (body === null) {
    throw new TimelineMemorySaveError(
      200,
      'Memory save acknowledgement was empty',
    );
  }
  let value: unknown;
  try {
    value = JSON.parse(body);
  } catch {
    throw new TimelineMemorySaveError(
      200,
      'Memory save acknowledgement was malformed',
    );
  }
  if (!isTrustedWriteAccepted(value)) {
    throw new TimelineMemorySaveError(
      200,
      'Memory save acknowledgement was unverified',
    );
  }
  return {
    id: value.applied.record_id,
    idempotent: value.idempotent,
  };
}

/** Save an explicit user assertion through native authenticated transport. */
export async function saveTimelineMemory(
  backend: OmiBackend,
  text: string,
  accountEpoch: number,
  clientWriteRef: string,
): Promise<SavedTimelineMemory> {
  if ((await backend.getApiContract?.()) !== 'canonical') {
    throw new TimelineMemorySaveError(
      0,
      'Memory saving is unavailable on this backend',
    );
  }
  if (
    backend.createWriteId === undefined ||
    !Number.isSafeInteger(accountEpoch) ||
    accountEpoch < 0 ||
    text.trim().length === 0 ||
    text.length > 4000 ||
    !/^[\x21-\x7e]{1,256}$/.test(clientWriteRef)
  ) {
    throw new TimelineMemorySaveError(
      422,
      'Memory note is invalid or unavailable',
    );
  }
  const writeId = await backend.createWriteId();
  if (!/^[0-9a-f]{64}$/.test(writeId)) {
    throw new TimelineMemorySaveError(
      0,
      'Native write identity is unavailable',
    );
  }
  const recordId = `timeline-${writeId.slice(0, 48)}`;
  let response;
  try {
    response = await backend.request({
      id: `memory-note-${writeId}`,
      method: 'POST',
      expectedApiContract: 'canonical',
      path: STM_NOTES_OPS_PATH,
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({
        write_id: writeId,
        account_epoch: accountEpoch,
        domain: 'stm-notes',
        op: {
          op: 'create',
          record_id: recordId,
          content: {
            text: text.trim(),
            client_write_ref: clientWriteRef,
          },
        },
      }),
    });
  } catch {
    throw new TimelineMemorySaveError(
      0,
      'Memory save could not be confirmed by the transport',
    );
  }
  if (response.status !== 200) {
    throw new TimelineMemorySaveError(
      response.status,
      response.status === 401
        ? 'Sign in again before saving a memory'
        : response.status === 503
        ? 'Memory saving is temporarily unavailable'
        : 'Memory could not be saved',
    );
  }
  return parseAccepted(response.body);
}
