import {encodeBase64} from './base64';
import type {NativeHttpResponse, OmiBackend} from './omiNative';

/**
 * Legacy omi (api.omi.me) offline sync for desktop ambient audio.
 *
 * The native spool stores framed packets exactly like wearable recordings —
 * `[seq u16 LE][fragment u8][opus bytes]` — while the legacy sync pipeline
 * consumes length-prefixed Opus WAL `.bin` files (`[len u32 LE][opus]` per
 * frame, decoded by backend `utils/sync/files.py`). This module re-frames
 * packets, uploads through `POST /v2/sync-local-files` (multipart, no
 * conversation binding: the server's 120 s gap split creates conversations),
 * then polls the returned job until the pipeline (VAD → STT → conversation →
 * memories) finishes. Uploads are plane-pinned with `expectedApiContract` so
 * a backend toggle mid-flight rejects instead of leaking audio to the wrong
 * plane.
 */

const POLL_ATTEMPTS = 12;
const POLL_FLOOR_MS = 1000;
const POLL_CEILING_MS = 15_000;

export class LegacyOmiSyncError extends Error {
  readonly transient: boolean;
  /** The segment can never be admitted (outside the recovery window). */
  readonly unrecoverable: boolean;

  constructor(
    message: string,
    options: {transient: boolean; unrecoverable?: boolean},
  ) {
    super(message);
    this.name = 'LegacyOmiSyncError';
    this.transient = options.transient;
    this.unrecoverable = options.unrecoverable === true;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => {
    setTimeout(resolve, ms);
  });
}

/** Converts wearable-framed packets into the backend's WAL byte format. */
export function omiWalFromFramedPackets(
  packets: readonly Uint8Array[],
): Uint8Array {
  let total = 0;
  for (const packet of packets) {
    if (packet.length < 3) {
      throw new Error('Ambient audio packet is truncated');
    }
    total += 4 + (packet.length - 3);
  }
  const wal = new Uint8Array(total);
  let cursor = 0;
  for (const packet of packets) {
    const size = packet.length - 3;
    wal[cursor] = size & 0xff;
    wal[cursor + 1] = (size >> 8) & 0xff;
    wal[cursor + 2] = (size >> 16) & 0xff;
    wal[cursor + 3] = (size >> 24) & 0xff;
    wal.set(packet.subarray(3), cursor + 4);
    cursor += 4 + size;
  }
  return wal;
}

/**
 * Filenames must end `_<unix-seconds-or-millis>.bin`; the timestamp drives
 * the server's fresh/backfill lane admission (`parse_sync_filename_timestamp`).
 */
export function omiSyncFilename(capturedAtMs: number): string {
  if (!Number.isSafeInteger(capturedAtMs) || capturedAtMs <= 0) {
    throw new Error('Ambient audio capture time is malformed');
  }
  return `omi-macos-ambient_${capturedAtMs}.bin`;
}

function parseJson(response: NativeHttpResponse, label: string): unknown {
  if (response.body === null) {
    throw new LegacyOmiSyncError(`${label} returned an empty body`, {
      transient: true,
    });
  }
  try {
    return JSON.parse(response.body) as unknown;
  } catch {
    throw new LegacyOmiSyncError(`${label} returned invalid JSON`, {
      transient: true,
    });
  }
}

function errorEnvelope(response: NativeHttpResponse): {code?: unknown} {
  const parsed = (() => {
    try {
      return response.body === null
        ? null
        : (JSON.parse(response.body) as unknown);
    } catch {
      return null;
    }
  })();
  if (parsed !== null && typeof parsed === 'object' && 'code' in parsed) {
    return parsed as {code?: unknown};
  }
  return {};
}

function statusError(response: NativeHttpResponse): LegacyOmiSyncError {
  const transient =
    response.status === 0 ||
    response.status === 408 ||
    response.status === 409 ||
    response.status === 429 ||
    response.status >= 500;
  const code = errorEnvelope(response).code;
  const unrecoverable =
    response.status === 422 && code === 'backfill_lookback_exceeded';
  return new LegacyOmiSyncError(
    `Legacy sync upload failed (${response.status})`,
    {transient, unrecoverable},
  );
}

async function pollSyncJob(
  backend: OmiBackend,
  jobId: string,
  firstDelayMs: number | null,
): Promise<void> {
  let delay = Math.min(
    POLL_CEILING_MS,
    Math.max(POLL_FLOOR_MS, firstDelayMs ?? 2000),
  );
  for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
    await sleep(delay);
    delay = Math.min(POLL_CEILING_MS, delay * 2);
    const response = await backend.request({
      id: `legacy-sync-job-${jobId}-${attempt}`,
      expectedApiContract: 'omi',
      method: 'GET',
      path: `/v2/sync-local-files/${encodeURIComponent(jobId)}`,
    });
    if (response.status === 200) {
      const job = parseJson(response, 'Legacy sync job') as {status?: unknown};
      if (job.status === 'completed') {
        return;
      }
      if (job.status === 'failed') {
        // The job consumed the audio but the pipeline failed; the content
        // claim re-admits a retry, so treat it as transient and re-upload.
        throw new LegacyOmiSyncError('Legacy sync job failed', {
          transient: true,
        });
      }
      continue;
    }
    if (response.status === 404) {
      // Job expired without a terminal state; re-uploading is content-deduped.
      throw new LegacyOmiSyncError('Legacy sync job expired', {
        transient: true,
      });
    }
    throw statusError(response);
  }
  throw new LegacyOmiSyncError('Legacy sync job is still processing', {
    transient: true,
  });
}

export async function syncLegacyOmiRecording(
  backend: OmiBackend,
  input: {capturedAtMs: number; packets: readonly Uint8Array[]},
): Promise<void> {
  const wal = omiWalFromFramedPackets(input.packets);
  const filename = omiSyncFilename(input.capturedAtMs);
  const response = await backend.request({
    id: `legacy-sync-${filename}`,
    expectedApiContract: 'omi',
    method: 'POST',
    path: '/v2/sync-local-files',
    multipart: [
      {
        name: 'files',
        filename,
        contentType: 'application/octet-stream',
        bytesBase64: encodeBase64(wal),
      },
    ],
  });
  if (response.status !== 202) {
    throw statusError(response);
  }
  const accepted = parseJson(response, 'Legacy sync upload') as {
    job_id?: unknown;
    status?: unknown;
    poll_after_ms?: unknown;
  };
  if (typeof accepted.job_id !== 'string' || accepted.job_id.length === 0) {
    throw new LegacyOmiSyncError('Legacy sync upload is malformed', {
      transient: true,
    });
  }
  if (accepted.status === 'completed') {
    // Content-claim dedupe: this audio already finished processing.
    return;
  }
  const pollAfter =
    typeof accepted.poll_after_ms === 'number' &&
    Number.isFinite(accepted.poll_after_ms)
      ? accepted.poll_after_ms
      : null;
  await pollSyncJob(backend, accepted.job_id, pollAfter);
}

export function isTransientLegacyOmiSyncError(error: unknown): boolean {
  if (error instanceof LegacyOmiSyncError) {
    return error.transient;
  }
  return (
    error instanceof TypeError ||
    (error !== null &&
      typeof error === 'object' &&
      'code' in error &&
      (error as {code: unknown}).code === 'OMI_HTTP_TRANSPORT')
  );
}
