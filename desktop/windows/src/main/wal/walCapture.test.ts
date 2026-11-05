import { describe, it, expect, beforeEach } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import { WalCapture } from './walCapture'
import { WAL_SCHEMA, getWal, listPendingWals, listWals, type WalDb } from './walStore'
import { WAL_CHUNK_SECONDS, WAL_NEW_FRAME_SYNC_DELAY_SECONDS } from '../../shared/wal'

const BYTES_PER_MS = 32
const CHUNK_MS = 250
const START = 1_723_800_000_000

let db: WalDb
let now = START
const written = new Map<string, Uint8Array>()

const capture = (over: { storeEverything?: boolean } = {}): WalCapture =>
  new WalCapture({
    db,
    writeFile: async (fileName, bytes) => {
      written.set(fileName, bytes)
      return bytes.byteLength
    },
    now: () => now,
    storeEverything: () => over.storeEverything ?? false
  })

/** Feeds `seconds` of audio with one disposition, advancing the clock. */
const feed = (
  wal: WalCapture,
  seconds: number,
  disposition: 'sent' | 'buffered' | 'missed',
  source = 'mic'
): void => {
  const chunks = Math.round((seconds * 1000) / CHUNK_MS)
  for (let i = 0; i < chunks; i += 1) {
    wal.observe({
      source,
      bytes: new Uint8Array(CHUNK_MS * BYTES_PER_MS).fill(7),
      byteLength: CHUNK_MS * BYTES_PER_MS,
      disposition
    })
    now += CHUNK_MS
  }
}

const settle = (): void => {
  now += WAL_NEW_FRAME_SYNC_DELAY_SECONDS * 1000 + 1000
}

beforeEach(() => {
  const database = new DatabaseSync(':memory:')
  database.exec(WAL_SCHEMA)
  db = database as unknown as WalDb
  now = START
  written.clear()
})

describe('keeping audio the socket did not take', () => {
  it('stores a window that was missed and queues it for upload', async () => {
    const wal = capture()
    feed(wal, WAL_CHUNK_SECONDS, 'missed')
    settle()

    const stored = await wal.flush('mic')
    expect(stored.length).toBe(1)
    const entry = stored[0]
    expect(entry.status).toBe('miss')
    expect(entry.device).toBe('mic')
    expect(entry.seconds).toBe(WAL_CHUNK_SECONDS)
    // The name carries the capture time the backend reads.
    expect(entry.filePath).toBe(`audio_mic_pcm16_16000_1_fs160_${Math.floor(START / 1000)}.bin`)
    // The bytes are on disk and indexed, so a restart can still upload them.
    expect(written.get(entry.filePath!)?.byteLength).toBe(WAL_CHUNK_SECONDS * 1000 * BYTES_PER_MS)
    expect(listPendingWals(db).length).toBe(1)
  })

  it('does not keep audio the socket took', async () => {
    const wal = capture()
    feed(wal, WAL_CHUNK_SECONDS, 'sent')
    settle()
    expect(await wal.flush('mic')).toEqual([])
    expect(listWals(db)).toEqual([])
    expect(written.size).toBe(0)
  })

  it('records a fully taken window as already synced when everything is retained', async () => {
    const wal = capture({ storeEverything: true })
    feed(wal, WAL_CHUNK_SECONDS, 'sent')
    settle()
    const [entry] = await wal.flush('mic')
    // Nothing to upload, but the capture is still accounted for.
    expect(entry.status).toBe('synced')
    expect(listPendingWals(db)).toEqual([])
  })

  it('keeps mic and system audio as separate recordings', async () => {
    const wal = capture()
    feed(wal, WAL_CHUNK_SECONDS, 'missed', 'mic')
    const micEnd = now
    now = START
    feed(wal, WAL_CHUNK_SECONDS, 'missed', 'system')
    now = Math.max(micEnd, now)
    settle()

    const stored = [...(await wal.flush('mic')), ...(await wal.flush('system'))]
    expect(stored.map((e) => e.device).sort()).toEqual(['mic', 'system'])
    // Two files, because they are two recordings that upload separately.
    expect(written.size).toBe(2)
  })
})

describe('pre-connect buffer resolution', () => {
  it('audio the socket flushed on open is not kept', async () => {
    const wal = capture()
    feed(wal, WAL_CHUNK_SECONDS, 'buffered')
    // The open handler flushed them, so they did reach the backend.
    wal.resolveBuffered('mic', 'sent')
    settle()
    expect(await wal.flush('mic')).toEqual([])
  })

  it('audio evicted past the buffer cap is kept', async () => {
    const wal = capture()
    feed(wal, WAL_CHUNK_SECONDS, 'buffered')
    // The bounded pre-connect buffer dropped the oldest chunks.
    wal.resolveBuffered('mic', 'missed')
    settle()
    const stored = await wal.flush('mic')
    expect(stored.length).toBe(1)
    expect(stored[0].status).toBe('miss')
  })

  it('resolving only part of the buffer keeps the rest pending', async () => {
    const wal = capture()
    feed(wal, WAL_CHUNK_SECONDS, 'buffered')
    wal.resolveBuffered('mic', 'sent', 40)
    settle()
    // The unresolved tail is still in flight, so nothing is judged yet.
    expect(await wal.flush('mic')).toEqual([])
    wal.resolveBuffered('mic', 'missed')
    const stored = await wal.flush('mic')
    expect(stored.length).toBe(1)
    expect(stored[0].syncedFrameOffset).toBe(40)
  })
})

describe('session end', () => {
  it('drains audio too short to have been judged', async () => {
    const wal = capture()
    feed(wal, 5, 'missed')
    // Under the window, so a normal flush stores nothing.
    expect(await wal.flush('mic')).toEqual([])
    const drained = await wal.drain('mic')
    expect(drained.length).toBe(1)
    expect(drained[0].seconds).toBe(5)
  })

  it('drainAll covers every capture source', async () => {
    const wal = capture()
    feed(wal, 5, 'missed', 'mic')
    feed(wal, 5, 'missed', 'system')
    const drained = await wal.drainAll()
    expect(drained.map((e) => e.device).sort()).toEqual(['mic', 'system'])
  })

  it('reset drops buffered audio without storing it', async () => {
    const wal = capture()
    feed(wal, WAL_CHUNK_SECONDS, 'missed')
    wal.reset()
    settle()
    expect(await wal.flush('mic')).toEqual([])
    expect(listWals(db)).toEqual([])
  })
})

describe('storage failures', () => {
  it('a failed write does not index a recording that has no bytes', async () => {
    const wal = new WalCapture({
      db,
      writeFile: async () => {
        throw new Error('disk full')
      },
      now: () => now
    })
    feed(wal, WAL_CHUNK_SECONDS, 'missed')
    settle()
    const stored = await wal.flush('mic')
    // Indexing it would leave a row pointing at a file that never existed,
    // which every later pass would try and fail to upload.
    expect(stored).toEqual([])
    expect(listWals(db)).toEqual([])
  })

  it('records the conversation a session was feeding', async () => {
    const wal = capture()
    wal.observe({
      source: 'mic',
      bytes: new Uint8Array(CHUNK_MS * BYTES_PER_MS),
      byteLength: CHUNK_MS * BYTES_PER_MS,
      disposition: 'missed',
      conversationId: 'conv-7'
    })
    now += CHUNK_MS
    feed(wal, 5, 'missed')
    const [entry] = await wal.drain('mic')
    // A recovered recording joins the conversation it belonged to instead of
    // becoming an orphan.
    expect(entry.conversationId).toBe('conv-7')
    expect(getWal(db, `mic_${entry.timerStart}`)?.conversationId).toBe('conv-7')
  })
})
