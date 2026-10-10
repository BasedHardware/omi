import { describe, it, expect, beforeEach } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import {
  WAL_SCHEMA,
  cleanupCandidates,
  deleteWal,
  getWal,
  listPendingWals,
  listUploadedWals,
  listWals,
  markMissingFilesCorrupted,
  markWalUploaded,
  recordWalRetry,
  resetWalRetries,
  setWalConversationId,
  setWalStatus,
  upsertWal,
  walStats,
  type WalDb
} from './walStore'
import { makeWalEntry, walId, type WalEntry } from '../../shared/wal'

let db: WalDb

const entry = (over: Partial<WalEntry> = {}): WalEntry => ({
  ...makeWalEntry({
    timerStart: 1_723_800_000,
    codec: 'pcm16',
    seconds: 60,
    frameSize: 160,
    totalFrames: 240,
    device: 'mic',
    status: 'miss',
    storage: 'disk',
    filePath: 'audio_mic_pcm16_16000_1_fs160_1723800000.bin',
    sizeBytes: 1_920_000
  }),
  ...over
})

beforeEach(() => {
  const database = new DatabaseSync(':memory:')
  database.exec(WAL_SCHEMA)
  db = database as unknown as WalDb
})

describe('upsert and read', () => {
  it('round-trips a recording', () => {
    const e = entry()
    const id = upsertWal(db, e)
    expect(id).toBe('mic_1723800000')
    const read = getWal(db, id)
    expect(read).toMatchObject({
      timerStart: e.timerStart,
      codec: 'pcm16',
      device: 'mic',
      status: 'miss',
      filePath: e.filePath,
      sizeBytes: 1_920_000
    })
  })

  it('re-chunking the same window updates in place instead of duplicating', () => {
    upsertWal(db, entry({ seconds: 30, totalFrames: 120 }))
    upsertWal(db, entry({ seconds: 60, totalFrames: 240, syncedFrameOffset: 10 }))
    expect(listWals(db).length).toBe(1)
    expect(getWal(db, 'mic_1723800000')).toMatchObject({ seconds: 60, syncedFrameOffset: 10 })
  })

  it('keeps a conversation id that a later upsert does not carry', () => {
    upsertWal(db, entry())
    setWalConversationId(db, 'mic_1723800000', 'conv-1')
    upsertWal(db, entry({ seconds: 90 }))
    // The live session stamped this; a re-chunk must not erase the link.
    expect(getWal(db, 'mic_1723800000')?.conversationId).toBe('conv-1')
  })

  it('separates recordings by capture source and start time', () => {
    upsertWal(db, entry())
    upsertWal(db, entry({ device: 'system' }))
    upsertWal(db, entry({ timerStart: 1_723_800_600 }))
    expect(listWals(db).length).toBe(3)
    expect(listWals(db)[0].timerStart).toBe(1_723_800_600)
  })
})

describe('pending work', () => {
  it('lists only recordings that still need an upload, oldest first', () => {
    upsertWal(db, entry({ timerStart: 300, status: 'miss' }))
    upsertWal(db, entry({ timerStart: 100, status: 'inProgress' }))
    upsertWal(db, entry({ timerStart: 200, status: 'synced' }))
    upsertWal(db, entry({ timerStart: 400, status: 'uploaded' }))
    upsertWal(db, entry({ timerStart: 500, status: 'corrupted' }))
    const pending = listPendingWals(db)
    // A backlog drains in capture order.
    expect(pending.map((w) => w.timerStart)).toEqual([100, 300])
  })

  it('skips recordings with no file on disk', () => {
    upsertWal(db, entry({ timerStart: 100, filePath: null }))
    expect(listPendingWals(db)).toEqual([])
  })

  it('honours the batch limit', () => {
    for (let i = 0; i < 10; i += 1) upsertWal(db, entry({ timerStart: 100 + i }))
    expect(listPendingWals(db, 4).length).toBe(4)
  })
})

describe('upload lifecycle', () => {
  it('a 202 records the job and keeps the file', () => {
    upsertWal(db, entry({ timerStart: 100 }))
    upsertWal(db, entry({ timerStart: 200 }))
    markWalUploaded(db, ['mic_100', 'mic_200'], 'job-1', 1_723_900_000)

    const uploaded = listUploadedWals(db)
    expect(uploaded.length).toBe(2)
    // Both entries share the batch's job id, which is how the reconciler
    // resolves them together.
    expect(uploaded.every((w) => w.jobId === 'job-1')).toBe(true)
    expect(uploaded[0].uploadedAt).toBe(1_723_900_000)
    // Still on disk: the job can fail, and these bytes are the only copy.
    expect(uploaded[0].filePath).not.toBeNull()
    expect(listPendingWals(db)).toEqual([])
  })

  it('a failed attempt counts a retry and releases the job', () => {
    upsertWal(db, entry({ timerStart: 100 }))
    markWalUploaded(db, ['mic_100'], 'job-1', 1_723_900_000)
    recordWalRetry(db, 'mic_100', 1_723_900_100)

    const after = getWal(db, 'mic_100')!
    expect(after.status).toBe('miss')
    expect(after.retryCount).toBe(1)
    expect(after.lastRetryAt).toBe(1_723_900_100)
    // A stale job id would make the reconciler resolve this against a job that
    // no longer owns it.
    expect(after.jobId).toBeNull()
    expect(listPendingWals(db).length).toBe(1)
  })

  it('a manual retry clears the attempt history', () => {
    upsertWal(db, entry({ timerStart: 100 }))
    recordWalRetry(db, 'mic_100', 1)
    recordWalRetry(db, 'mic_100', 2)
    recordWalRetry(db, 'mic_100', 3)
    resetWalRetries(db, 'mic_100')
    const after = getWal(db, 'mic_100')!
    expect(after.retryCount).toBe(0)
    expect(after.status).toBe('miss')
  })
})

describe('cleanup', () => {
  it('offers only confirmed recordings older than the cutoff', () => {
    upsertWal(db, entry({ timerStart: 100, status: 'synced' }))
    upsertWal(db, entry({ timerStart: 900, status: 'synced' }))
    upsertWal(db, entry({ timerStart: 100, device: 'system', status: 'uploaded' }))
    upsertWal(db, entry({ timerStart: 100, device: 'other', status: 'miss' }))

    const candidates = cleanupCandidates(db, 500)
    // Only the old, confirmed one. Deleting an "uploaded" recording would throw
    // away the only copy of audio whose job can still fail.
    expect(candidates.map((w) => walId(w))).toEqual(['mic_100'])
  })

  it('marks recordings whose file vanished as corrupted', () => {
    upsertWal(db, entry({ timerStart: 100 }))
    upsertWal(db, entry({ timerStart: 200 }))
    upsertWal(db, entry({ timerStart: 300, status: 'synced' }))
    const present = new Set(['audio_mic_pcm16_16000_1_fs160_1723800000.bin'])

    const corrupted = markMissingFilesCorrupted(db, (name) => present.has(name))
    // Both pending rows point at the same missing name in this fixture.
    expect(corrupted.length).toBe(0)

    upsertWal(db, entry({ timerStart: 400, filePath: 'gone.bin' }))
    const nowCorrupted = markMissingFilesCorrupted(db, (name) => present.has(name))
    expect(nowCorrupted).toEqual(['mic_400'])
    expect(getWal(db, 'mic_400')?.status).toBe('corrupted')
    // A recording with no bytes can never upload, so it leaves the queue.
    expect(listPendingWals(db).some((w) => walId(w) === 'mic_400')).toBe(false)
  })

  it('deleting removes the row', () => {
    upsertWal(db, entry())
    deleteWal(db, 'mic_1723800000')
    expect(getWal(db, 'mic_1723800000')).toBeNull()
  })
})

describe('stats', () => {
  it('counts each state and the bytes held', () => {
    upsertWal(db, entry({ timerStart: 100, status: 'miss', sizeBytes: 1000 }))
    upsertWal(db, entry({ timerStart: 200, status: 'inProgress', sizeBytes: 2000 }))
    upsertWal(db, entry({ timerStart: 300, status: 'uploaded', sizeBytes: 3000 }))
    upsertWal(db, entry({ timerStart: 400, status: 'synced', sizeBytes: 4000 }))
    upsertWal(db, entry({ timerStart: 500, status: 'corrupted', sizeBytes: 5000 }))
    upsertWal(db, entry({ timerStart: 600, status: 'outsideRecoveryWindow', sizeBytes: 6000 }))

    expect(walStats(db)).toEqual({
      total: 6,
      pending: 2,
      uploaded: 1,
      synced: 1,
      failed: 2,
      bytes: 21_000
    })
  })

  it('is empty on a fresh database', () => {
    expect(walStats(db)).toEqual({
      total: 0,
      pending: 0,
      uploaded: 0,
      synced: 0,
      failed: 0,
      bytes: 0
    })
  })
})

describe('status transitions', () => {
  it('setWalStatus moves a recording between states', () => {
    upsertWal(db, entry())
    setWalStatus(db, 'mic_1723800000', 'outsideRecoveryWindow')
    expect(getWal(db, 'mic_1723800000')?.status).toBe('outsideRecoveryWindow')
    // Permanently refused audio leaves the queue but keeps its file.
    expect(listPendingWals(db)).toEqual([])
    expect(getWal(db, 'mic_1723800000')?.filePath).not.toBeNull()
  })
})
