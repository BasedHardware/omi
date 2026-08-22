import { describe, it, expect } from 'vitest'
import {
  DEFAULT_RETRY_AFTER_SECONDS,
  MAX_RETRY_AFTER_SECONDS,
  RETRY_BACKOFF_SECONDS,
  canAttemptUpload,
  classifyJobStatus,
  classifyUploadResponse,
  nextStatusForJobOutcome,
  retryDelaySeconds
} from './syncPolicy'
import { WAL_MAX_AUTO_RETRIES } from '../../shared/wal'

const withHeaders = (
  status: number,
  body: unknown,
  headers: Record<string, string> = {}
): { status: number; body: unknown; header: (n: string) => string | null } => ({
  status,
  body,
  header: (name) => headers[name.toLowerCase()] ?? null
})

describe('classifyUploadResponse', () => {
  it('reads a 202 as accepted with its job id and poll delay', () => {
    const outcome = classifyUploadResponse(
      withHeaders(202, {
        job_id: 'job-1',
        status: 'queued',
        total_files: 2,
        total_segments: 4,
        poll_after_ms: 3000,
        lane: 'fresh'
      })
    )
    expect(outcome).toEqual({ kind: 'accepted', jobId: 'job-1', pollAfterMs: 3000, lane: 'fresh' })
  })

  it('refuses to treat a 202 with no job id as accepted', () => {
    // Marking this uploaded would strand the recording: nothing could ever
    // resolve it, and its file would never be released or retried.
    const outcome = classifyUploadResponse(withHeaders(202, { status: 'queued' }))
    expect(outcome.kind).toBe('transient')
  })

  it('defaults the poll delay when the server omits it', () => {
    const outcome = classifyUploadResponse(withHeaders(202, { job_id: 'j' }))
    expect(outcome).toMatchObject({ kind: 'accepted', pollAfterMs: 2000 })
  })

  it('treats the lookback refusal as permanent', () => {
    const outcome = classifyUploadResponse(
      withHeaders(422, {
        code: 'backfill_lookback_exceeded',
        detail:
          'Recording is older than the automatic recovery window; local audio was not consumed'
      })
    )
    expect(outcome).toEqual({ kind: 'refusedPermanently', reason: 'backfill_lookback_exceeded' })
  })

  it('honours a pause the server asks for, and its Retry-After', () => {
    // "Sync is briefly pausing safely; local audio was not consumed"
    const cutover = classifyUploadResponse(
      withHeaders(503, { code: 'sync_ledger_fence_cutover' }, { 'retry-after': '60' })
    )
    expect(cutover).toEqual({
      kind: 'retryAfter',
      seconds: 60,
      reason: 'sync_ledger_fence_cutover'
    })

    const capacity = classifyUploadResponse(
      withHeaders(503, { code: 'backfill_capacity' }, { 'retry-after': '3600' })
    )
    expect(capacity).toEqual({ kind: 'retryAfter', seconds: 3600, reason: 'backfill_capacity' })

    const rateLimited = classifyUploadResponse(withHeaders(429, {}, { 'retry-after': '30' }))
    expect(rateLimited).toMatchObject({ kind: 'retryAfter', seconds: 30 })
  })

  it('falls back to a default pause and clamps an absurd one', () => {
    expect(classifyUploadResponse(withHeaders(503, {}))).toMatchObject({
      kind: 'retryAfter',
      seconds: DEFAULT_RETRY_AFTER_SECONDS
    })
    expect(
      classifyUploadResponse(withHeaders(503, {}, { 'retry-after': '999999999' }))
    ).toMatchObject({ seconds: MAX_RETRY_AFTER_SECONDS })
    expect(classifyUploadResponse(withHeaders(503, {}, { 'retry-after': 'soon' }))).toMatchObject({
      seconds: DEFAULT_RETRY_AFTER_SECONDS
    })
  })

  it('separates an identity rejection from a transient failure', () => {
    expect(classifyUploadResponse(withHeaders(401, {})).kind).toBe('notAuthorized')
    expect(classifyUploadResponse(withHeaders(403, {})).kind).toBe('notAuthorized')
  })

  it('keeps the recording for anything it cannot read as success', () => {
    for (const status of [400, 404, 409, 418, 500, 502]) {
      const outcome = classifyUploadResponse(withHeaders(status, {}))
      // Never "accepted": the bytes are still the client's responsibility.
      expect(outcome.kind).toBe('transient')
    }
  })
})

describe('classifyJobStatus', () => {
  it('keeps polling while the job runs', () => {
    expect(classifyJobStatus({ status: 200, body: { status: 'queued' } }).kind).toBe('pending')
    expect(classifyJobStatus({ status: 200, body: { status: 'processing' } }).kind).toBe('pending')
  })

  it('resolves a completed job as success', () => {
    expect(classifyJobStatus({ status: 200, body: { status: 'completed' } }).kind).toBe('succeeded')
  })

  it('treats a partial failure as success only when something landed', () => {
    // Re-uploading would duplicate the conversation that already exists.
    expect(
      classifyJobStatus({
        status: 200,
        body: { status: 'partial_failure', successful_segments: 2, failed_segments: 1 }
      }).kind
    ).toBe('succeeded')
    expect(
      classifyJobStatus({
        status: 200,
        body: { status: 'partial_failure', successful_segments: 0, failed_segments: 3 }
      }).kind
    ).toBe('failed')
  })

  it('separates a retryable failure from a permanent refusal', () => {
    expect(classifyJobStatus({ status: 200, body: { status: 'failed' } })).toEqual({
      kind: 'failed',
      reason: 'failed'
    })
    expect(
      classifyJobStatus({
        status: 200,
        body: { status: 'failed', reason_code: 'backfill_lookback_exceeded' }
      }).kind
    ).toBe('refusedPermanently')
  })

  it('carries the server error text into the failure reason', () => {
    expect(
      classifyJobStatus({ status: 200, body: { status: 'failed', error: 'stt upstream error' } })
    ).toEqual({ kind: 'failed', reason: 'stt upstream error' })
  })

  it('a missing or foreign job returns the recording to the queue', () => {
    // Otherwise its audio waits forever on a job that will never answer.
    expect(classifyJobStatus({ status: 404 }).kind).toBe('unknownJob')
    expect(classifyJobStatus({ status: 403 }).kind).toBe('unknownJob')
  })

  it('a transient fetch failure changes nothing', () => {
    expect(classifyJobStatus({ status: 500 }).kind).toBe('pending')
    expect(classifyJobStatus({ status: 0 }).kind).toBe('pending')
  })

  it('an unrecognized status is not read as success', () => {
    // Guessing success here would delete audio the server is still working on.
    expect(classifyJobStatus({ status: 200, body: { status: 'something_new' } }).kind).toBe(
      'pending'
    )
    expect(classifyJobStatus({ status: 200, body: {} }).kind).toBe('pending')
  })
})

describe('nextStatusForJobOutcome', () => {
  it('maps each outcome to the state the recording takes', () => {
    expect(nextStatusForJobOutcome({ kind: 'pending' })).toBeNull()
    expect(nextStatusForJobOutcome({ kind: 'succeeded' })).toBe('synced')
    expect(nextStatusForJobOutcome({ kind: 'refusedPermanently', reason: 'x' })).toBe(
      'outsideRecoveryWindow'
    )
    expect(nextStatusForJobOutcome({ kind: 'failed', reason: 'x' })).toBe('miss')
    expect(nextStatusForJobOutcome({ kind: 'unknownJob' })).toBe('miss')
  })
})

describe('attempt scheduling', () => {
  it('the first attempt is immediate and later ones back off', () => {
    expect(retryDelaySeconds(0)).toBe(0)
    expect(retryDelaySeconds(1)).toBe(RETRY_BACKOFF_SECONDS[1])
    expect(retryDelaySeconds(2)).toBe(RETRY_BACKOFF_SECONDS[2])
    // Past the table the longest delay holds rather than throwing.
    expect(retryDelaySeconds(99)).toBe(RETRY_BACKOFF_SECONDS[RETRY_BACKOFF_SECONDS.length - 1])
  })

  it('waits out the backoff before the next attempt', () => {
    const base = { nowSeconds: 1_000, retryCount: 1 }
    expect(canAttemptUpload({ ...base, lastRetryAt: 1_000 })).toBe(false)
    expect(canAttemptUpload({ ...base, lastRetryAt: 1_000 - RETRY_BACKOFF_SECONDS[1] })).toBe(true)
  })

  it('stops automatic attempts at the ceiling so a person can decide', () => {
    expect(
      canAttemptUpload({ retryCount: WAL_MAX_AUTO_RETRIES, lastRetryAt: 0, nowSeconds: 1_000_000 })
    ).toBe(false)
  })

  it('respects a pause the server asked for, whatever the backoff says', () => {
    expect(
      canAttemptUpload({
        retryCount: 0,
        lastRetryAt: 0,
        nowSeconds: 1_000,
        pausedUntilSeconds: 1_100
      })
    ).toBe(false)
    expect(
      canAttemptUpload({
        retryCount: 0,
        lastRetryAt: 0,
        nowSeconds: 1_100,
        pausedUntilSeconds: 1_100
      })
    ).toBe(true)
  })
})
