/**
 * Every decision the offline-audio sync makes, as pure functions: how to read
 * an upload response, how to read a job's status, and when the next attempt is
 * allowed. Kept free of I/O so the wire contract is testable exactly, mirroring
 * macOS `WAL/WALCloudSyncLogic.swift`.
 *
 * The governing rule from the backend: every refusal says "local audio was not
 * consumed". A response this code cannot confidently read as success must
 * therefore keep the recording, never drop it.
 */

import { WAL_MAX_AUTO_RETRIES, type WalStatus } from '../../shared/wal'

// --- upload response ---------------------------------------------------------

export type UploadOutcome =
  /** 202: the server has the bytes and a job owns the result. */
  | { kind: 'accepted'; jobId: string; pollAfterMs: number; lane: string }
  /** Refused for good (older than the recovery window). Keep the file, stop trying. */
  | { kind: 'refusedPermanently'; reason: string }
  /** Refused for now. Keep the file and come back after the given delay. */
  | { kind: 'retryAfter'; seconds: number; reason: string }
  /** The identity was rejected; retrying without a fresh token is pointless. */
  | { kind: 'notAuthorized' }
  /** Anything else: assume the audio is still ours and try again later. */
  | { kind: 'transient'; reason: string }

export interface UploadResponseLike {
  status: number
  /** Parsed JSON body, when there was one. */
  body?: unknown
  header?: (name: string) => string | null
}

/** Backend default when it asks for a pause without naming one. */
export const DEFAULT_RETRY_AFTER_SECONDS = 60
/** Upper bound so a hostile or mistaken header cannot park sync for days. */
export const MAX_RETRY_AFTER_SECONDS = 6 * 60 * 60

const readRetryAfter = (response: UploadResponseLike): number | null => {
  const raw = response.header?.('retry-after') ?? null
  if (raw === null) return null
  const seconds = Number(raw)
  if (!Number.isFinite(seconds) || seconds <= 0) return null
  return Math.min(MAX_RETRY_AFTER_SECONDS, Math.round(seconds))
}

const bodyField = (body: unknown, key: string): unknown =>
  body !== null && typeof body === 'object' ? (body as Record<string, unknown>)[key] : undefined

const bodyString = (body: unknown, key: string): string | null => {
  const value = bodyField(body, key)
  return typeof value === 'string' && value.length > 0 ? value : null
}

export function classifyUploadResponse(response: UploadResponseLike): UploadOutcome {
  const code = bodyString(response.body, 'code')

  if (response.status === 202) {
    const jobId = bodyString(response.body, 'job_id')
    if (jobId === null) {
      // Accepted without a job id would leave the recording stuck as uploaded
      // with nothing able to resolve it, so treat it as not accepted at all.
      return { kind: 'transient', reason: 'accepted_without_job_id' }
    }
    const pollAfter = bodyField(response.body, 'poll_after_ms')
    const lane = bodyString(response.body, 'lane') ?? 'fresh'
    return {
      kind: 'accepted',
      jobId,
      pollAfterMs:
        typeof pollAfter === 'number' && Number.isFinite(pollAfter) && pollAfter > 0
          ? pollAfter
          : 2000,
      lane
    }
  }

  // Older than the automatic-recovery window. The file stays on disk, but no
  // number of retries can make the server take it.
  if (response.status === 422 && code === 'backfill_lookback_exceeded') {
    return { kind: 'refusedPermanently', reason: code }
  }

  if (response.status === 401 || response.status === 403) {
    return { kind: 'notAuthorized' }
  }

  if (response.status === 429 || response.status === 503) {
    return {
      kind: 'retryAfter',
      seconds: readRetryAfter(response) ?? DEFAULT_RETRY_AFTER_SECONDS,
      reason: code ?? String(response.status)
    }
  }

  // Any other 4xx is a client-side problem this build cannot fix by retrying
  // immediately, but the audio is still ours; treat it as transient so the
  // recording is kept and the backoff ladder applies.
  return { kind: 'transient', reason: code ?? `http_${response.status}` }
}

// --- job status --------------------------------------------------------------

export type JobOutcome =
  /** Still running; poll again. */
  | { kind: 'pending' }
  /** The conversation exists; the local audio can be released. */
  | { kind: 'succeeded' }
  /** The job failed; the recording goes back in the queue. */
  | { kind: 'failed'; reason: string }
  /** The job failed and retrying cannot help. */
  | { kind: 'refusedPermanently'; reason: string }
  /** The job is gone or not ours; the recording goes back in the queue so its
   *  audio is not stranded waiting on a job that will never answer. */
  | { kind: 'unknownJob' }

export interface JobStatusLike {
  status?: unknown
  successful_segments?: unknown
  failed_segments?: unknown
  reason_code?: unknown
  error?: unknown
}

export function classifyJobStatus(
  response: { status: number; body?: JobStatusLike } | { status: number; body?: unknown }
): JobOutcome {
  if (response.status === 404 || response.status === 403) return { kind: 'unknownJob' }
  if (response.status < 200 || response.status >= 300) {
    // A transient fetch failure must not move the recording: mac's reconciler
    // makes no change on one, and neither does this.
    return { kind: 'pending' }
  }
  const body = (response.body ?? {}) as JobStatusLike
  const status = typeof body.status === 'string' ? body.status : ''
  const reason = typeof body.reason_code === 'string' ? body.reason_code : null
  const successful = typeof body.successful_segments === 'number' ? body.successful_segments : 0

  switch (status) {
    case 'queued':
    case 'processing':
      return { kind: 'pending' }
    case 'completed':
    case 'success':
      return { kind: 'succeeded' }
    case 'partial_failure':
      // Some segments became a conversation. Re-uploading the whole recording
      // would duplicate what already landed, so this is terminal on success and
      // retryable only when nothing landed at all.
      return successful > 0
        ? { kind: 'succeeded' }
        : { kind: 'failed', reason: reason ?? 'partial_failure' }
    case 'failed':
      if (reason === 'backfill_lookback_exceeded') {
        return { kind: 'refusedPermanently', reason }
      }
      return { kind: 'failed', reason: reason ?? textOf(body.error) ?? 'failed' }
    default:
      // An unrecognized status is not evidence of success, and treating it as
      // failure would re-upload audio the server may be processing.
      return { kind: 'pending' }
  }
}

const textOf = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null

/** The status a recording takes after an outcome. */
export function nextStatusForJobOutcome(outcome: JobOutcome): WalStatus | null {
  switch (outcome.kind) {
    case 'pending':
      return null
    case 'succeeded':
      return 'synced'
    case 'refusedPermanently':
      return 'outsideRecoveryWindow'
    case 'failed':
    case 'unknownJob':
      return 'miss'
  }
}

// --- attempt scheduling -------------------------------------------------------

/** Backoff between automatic attempts, in seconds, indexed by attempts made. */
export const RETRY_BACKOFF_SECONDS = [0, 60, 300, 900] as const

export function retryDelaySeconds(retryCount: number): number {
  const index = Math.min(Math.max(retryCount, 0), RETRY_BACKOFF_SECONDS.length - 1)
  return RETRY_BACKOFF_SECONDS[index]
}

export interface AttemptGateInput {
  retryCount: number
  lastRetryAt: number
  nowSeconds: number
  /** Set while the backend has asked for a pause. */
  pausedUntilSeconds?: number
}

/**
 * Whether a recording may be attempted now. Automatic attempts stop at the
 * retry ceiling: past it the recording is presented as failed and waits for a
 * person, rather than uploading the same bytes forever.
 */
export function canAttemptUpload(input: AttemptGateInput): boolean {
  if (input.pausedUntilSeconds !== undefined && input.nowSeconds < input.pausedUntilSeconds) {
    return false
  }
  if (input.retryCount >= WAL_MAX_AUTO_RETRIES) return false
  const delay = retryDelaySeconds(input.retryCount)
  if (delay === 0) return true
  return input.nowSeconds - input.lastRetryAt >= delay
}
