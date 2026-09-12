import { describe, it, expect, beforeEach } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import { WalSyncEngine, type WalSyncHttp, type WalUploadFile } from './syncEngine'
import {
  WAL_SCHEMA,
  getWal,
  listPendingWals,
  markWalUploaded,
  upsertWal,
  type WalDb
} from './walStore'
import { makeWalEntry, walFileName, type WalEntry } from '../../shared/wal'

let db: WalDb
let now = 1_723_900_000

const entryFor = (timerStart: number, over: Partial<WalEntry> = {}): WalEntry => {
  const base = makeWalEntry({
    timerStart,
    codec: 'pcm16',
    seconds: 60,
    frameSize: 160,
    totalFrames: 240,
    device: 'mic',
    status: 'miss',
    storage: 'disk',
    sizeBytes: 1000
  })
  return { ...base, filePath: walFileName(base), ...over }
}

interface Harness {
  engine: WalSyncEngine
  uploads: Array<{ files: WalUploadFile[]; conversationId: string | null; manifest: string | null }>
  jobPolls: string[]
  deleted: string[]
  setUploadResponse: (r: {
    status: number
    body?: unknown
    headers?: Record<string, string>
  }) => void
  setJobResponse: (r: { status: number; body?: unknown }) => void
  setManifest: (m: string | null) => void
  missingFiles: Set<string>
}

const harness = (over: { batchSize?: number } = {}): Harness => {
  const uploads: Harness['uploads'] = []
  const jobPolls: string[] = []
  const deleted: string[] = []
  const missingFiles = new Set<string>()
  let uploadResponse: { status: number; body?: unknown; headers?: Record<string, string> } = {
    status: 202,
    body: { job_id: 'job-1', poll_after_ms: 1000, lane: 'fresh' }
  }
  let jobResponse: { status: number; body?: unknown } = {
    status: 200,
    body: { status: 'processing' }
  }
  let manifest: string | null = 'manifest-token'

  const http: WalSyncHttp = {
    uploadFiles: async (args) => {
      uploads.push(args)
      return {
        status: uploadResponse.status,
        body: uploadResponse.body,
        header: (name) => uploadResponse.headers?.[name.toLowerCase()] ?? null
      }
    },
    fetchJobStatus: async (jobId) => {
      jobPolls.push(jobId)
      return jobResponse
    },
    requestCaptureManifest: async () => manifest
  }

  const engine = new WalSyncEngine({
    db,
    http,
    readFile: async (fileName) =>
      missingFiles.has(fileName) ? null : new Uint8Array([1, 2, 3, 4]),
    deleteFile: async (fileName) => {
      deleted.push(fileName)
    },
    fileExists: (fileName) => !missingFiles.has(fileName),
    nowSeconds: () => now,
    batchSize: over.batchSize
  })

  return {
    engine,
    uploads,
    jobPolls,
    deleted,
    missingFiles,
    setUploadResponse: (r) => {
      uploadResponse = r
    },
    setJobResponse: (r) => {
      jobResponse = r
    },
    setManifest: (m) => {
      manifest = m
    }
  }
}

beforeEach(() => {
  const database = new DatabaseSync(':memory:')
  database.exec(WAL_SCHEMA)
  db = database as unknown as WalDb
  now = 1_723_900_000
})

describe('upload pass', () => {
  it('sends a batch with a capture manifest and records the job on a 202', async () => {
    const h = harness({ batchSize: 2 })
    upsertWal(db, entryFor(100))
    upsertWal(db, entryFor(200))
    upsertWal(db, entryFor(300))

    const result = await h.engine.syncPending()
    expect(result).toMatchObject({ attempted: 2, accepted: 2 })
    // Oldest first, so a backlog drains in capture order.
    expect(h.uploads[0].files.map((f) => f.fileName)).toEqual([
      walFileName(entryFor(100)),
      walFileName(entryFor(200))
    ])
    expect(h.uploads[0].manifest).toBe('manifest-token')

    // Both share the batch's job id and keep their files.
    const first = getWal(db, 'mic_100')!
    expect(first).toMatchObject({ status: 'uploaded', jobId: 'job-1', uploadedAt: now })
    expect(first.filePath).not.toBeNull()
    expect(getWal(db, 'mic_200')?.jobId).toBe('job-1')
    // The third is still queued.
    expect(listPendingWals(db).map((w) => w.timerStart)).toEqual([300])
  })

  it('uploads without a manifest rather than not at all', async () => {
    const h = harness()
    h.setManifest(null)
    upsertWal(db, entryFor(100))
    const result = await h.engine.syncPending()
    // Losing the trusted lane is a downgrade; losing the upload is data loss.
    expect(result.accepted).toBe(1)
    expect(h.uploads[0].manifest).toBeNull()
  })

  it('attaches a conversation id only when the whole batch shares one', async () => {
    const h = harness({ batchSize: 3 })
    upsertWal(db, entryFor(100, { conversationId: 'conv-a' }))
    upsertWal(db, entryFor(200, { conversationId: 'conv-a' }))
    await h.engine.syncPending()
    expect(h.uploads[0].conversationId).toBe('conv-a')

    upsertWal(db, entryFor(300, { conversationId: 'conv-a' }))
    upsertWal(db, entryFor(400, { conversationId: 'conv-b' }))
    await h.engine.syncPending()
    // The endpoint attaches the whole upload to one conversation, so a mixed
    // batch must not claim either.
    expect(h.uploads[1].conversationId).toBeNull()
  })

  it('a permanent refusal keeps the file and stops retrying', async () => {
    const h = harness()
    h.setUploadResponse({ status: 422, body: { code: 'backfill_lookback_exceeded' } })
    upsertWal(db, entryFor(100))

    await h.engine.syncPending()
    const after = getWal(db, 'mic_100')!
    expect(after.status).toBe('outsideRecoveryWindow')
    expect(after.filePath).not.toBeNull()
    expect(listPendingWals(db)).toEqual([])
  })

  it('a requested pause defers without spending a retry', async () => {
    const h = harness()
    h.setUploadResponse({
      status: 503,
      body: { code: 'sync_ledger_fence_cutover' },
      headers: { 'retry-after': '60' }
    })
    upsertWal(db, entryFor(100))

    const result = await h.engine.syncPending()
    expect(result.deferred).toBe(true)
    expect(h.engine.isPaused).toBe(true)
    // The server refused to look at the audio; charging a retry would spend the
    // budget on its capacity rather than on this recording.
    expect(getWal(db, 'mic_100')).toMatchObject({ status: 'miss', retryCount: 0 })

    // A later pass does nothing until the pause elapses.
    await h.engine.syncPending()
    expect(h.uploads.length).toBe(1)
    now += 61
    h.setUploadResponse({ status: 202, body: { job_id: 'job-9' } })
    await h.engine.syncPending()
    expect(h.uploads.length).toBe(2)
  })

  it('an identity rejection leaves the recording untouched', async () => {
    const h = harness()
    h.setUploadResponse({ status: 401 })
    upsertWal(db, entryFor(100))
    const result = await h.engine.syncPending()
    expect(result.deferred).toBe(true)
    // A fresh token may fix this, so nothing is charged against the recording.
    expect(getWal(db, 'mic_100')).toMatchObject({ status: 'miss', retryCount: 0 })
  })

  it('a transient failure charges a retry and backs off', async () => {
    const h = harness()
    h.setUploadResponse({ status: 500 })
    upsertWal(db, entryFor(100))

    await h.engine.syncPending()
    expect(getWal(db, 'mic_100')).toMatchObject({ status: 'miss', retryCount: 1 })
    // Immediately after, the backoff holds it back.
    await h.engine.syncPending()
    expect(h.uploads.length).toBe(1)

    now += 60
    await h.engine.syncPending()
    expect(h.uploads.length).toBe(2)
  })

  it('stops attempting once the automatic budget is spent', async () => {
    const h = harness()
    h.setUploadResponse({ status: 500 })
    upsertWal(db, entryFor(100))
    for (let i = 0; i < 6; i += 1) {
      now += 3600
      await h.engine.syncPending()
    }
    // Three automatic attempts, then it waits for a person.
    expect(h.uploads.length).toBe(3)
    expect(getWal(db, 'mic_100')?.retryCount).toBe(3)
  })

  it('marks a recording corrupted when its bytes are gone', async () => {
    const h = harness()
    const missing = entryFor(100)
    upsertWal(db, missing)
    h.missingFiles.add(missing.filePath!)

    const result = await h.engine.syncPending()
    expect(result.attempted).toBe(0)
    expect(h.uploads.length).toBe(0)
    expect(getWal(db, 'mic_100')?.status).toBe('corrupted')
  })

  it('refuses to run two passes at once', async () => {
    const h = harness()
    upsertWal(db, entryFor(100))
    const [first, second] = await Promise.all([h.engine.syncPending(), h.engine.syncPending()])
    // A second concurrent pass would re-send the same audio and duplicate the
    // conversation it becomes.
    expect(h.uploads.length).toBe(1)
    expect([first.accepted, second.accepted].sort()).toEqual([0, 1])
  })
})

describe('reconciliation', () => {
  const uploadTwo = (): void => {
    upsertWal(db, entryFor(100))
    upsertWal(db, entryFor(200))
    markWalUploaded(db, ['mic_100', 'mic_200'], 'job-1', now)
  }

  it('polls each job once and applies it to every recording that shares it', async () => {
    const h = harness()
    uploadTwo()
    h.setJobResponse({ status: 200, body: { status: 'completed' } })

    expect(await h.engine.reconcileUploaded()).toBe(2)
    expect(h.jobPolls).toEqual(['job-1'])
    expect(getWal(db, 'mic_100')?.status).toBe('synced')
    expect(getWal(db, 'mic_200')?.status).toBe('synced')
  })

  it('leaves a running job alone', async () => {
    const h = harness()
    uploadTwo()
    h.setJobResponse({ status: 200, body: { status: 'processing' } })
    expect(await h.engine.reconcileUploaded()).toBe(0)
    expect(getWal(db, 'mic_100')?.status).toBe('uploaded')
  })

  it('a transient poll failure changes nothing', async () => {
    const h = harness()
    uploadTwo()
    h.setJobResponse({ status: 500 })
    expect(await h.engine.reconcileUploaded()).toBe(0)
    expect(getWal(db, 'mic_100')?.status).toBe('uploaded')
  })

  it('a failed job returns the recording to the queue with an attempt spent', async () => {
    const h = harness()
    uploadTwo()
    h.setJobResponse({ status: 200, body: { status: 'failed', error: 'stt upstream error' } })

    expect(await h.engine.reconcileUploaded()).toBe(2)
    const after = getWal(db, 'mic_100')!
    expect(after.status).toBe('miss')
    expect(after.retryCount).toBe(1)
    // A job that keeps failing must eventually surface instead of looping.
    expect(after.jobId).toBeNull()
  })

  it('a job that no longer exists releases the recording', async () => {
    const h = harness()
    uploadTwo()
    h.setJobResponse({ status: 404 })
    expect(await h.engine.reconcileUploaded()).toBe(2)
    // Otherwise its audio waits forever on a job that will never answer.
    expect(getWal(db, 'mic_100')?.status).toBe('miss')
  })

  it('a permanently refused job stops retrying but keeps the file', async () => {
    const h = harness()
    uploadTwo()
    h.setJobResponse({
      status: 200,
      body: { status: 'failed', reason_code: 'backfill_lookback_exceeded' }
    })
    await h.engine.reconcileUploaded()
    expect(getWal(db, 'mic_100')?.status).toBe('outsideRecoveryWindow')
    expect(getWal(db, 'mic_100')?.filePath).not.toBeNull()
  })

  it('does nothing when there is nothing uploaded', async () => {
    const h = harness()
    expect(await h.engine.reconcileUploaded()).toBe(0)
    expect(h.jobPolls).toEqual([])
  })
})

describe('cleanup', () => {
  it('releases only confirmed recordings', async () => {
    const h = harness()
    const synced = entryFor(100, { status: 'synced' })
    const uploaded = entryFor(200, { status: 'uploaded' })
    upsertWal(db, synced)
    upsertWal(db, uploaded)

    const removed = await h.engine.cleanupConfirmed([synced, uploaded])
    expect(removed).toBe(1)
    // Deleting the uploaded one would throw away audio whose job can still fail.
    expect(h.deleted).toEqual([synced.filePath])
  })
})
