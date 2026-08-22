import { describe, it, expect } from 'vitest'
import { RingDrain, type DrainSink, type StorageTransport } from './ringDrain'
import { RING_RECORD_BYTES } from './storageProtocol'
import type { DrainedChunk } from './storageChunker'

const FRAMES_PER_SECOND = 50
const EPOCH = 1_723_800_000

/** One 444 byte ring record: big-endian timestamp then a packed payload. */
const ringRecord = (epoch: number, frames: number[][]): Uint8Array => {
  const record = new Uint8Array(RING_RECORD_BYTES)
  new DataView(record.buffer).setUint32(0, epoch, false)
  let offset = 4
  for (const frame of frames) {
    record[offset] = frame.length
    record.set(frame, offset + 1)
    offset += 1 + frame.length
  }
  return record
}

const statusBytes = (
  over: Partial<{ used: number; unread: number; free: number; rtc: number }> = {}
): Uint8Array => {
  const bytes = new Uint8Array(16)
  const view = new DataView(bytes.buffer)
  view.setUint32(0, over.used ?? 4_000, true)
  view.setUint32(4, over.unread ?? 3, true)
  view.setUint32(8, over.free ?? 1_000, true)
  view.setUint32(12, over.rtc ?? 1, true)
  return bytes
}

const infoNotification = (readSeq: number): Uint8Array => {
  const bytes = new Uint8Array(31)
  bytes[0] = 0x02
  new DataView(bytes.buffer).setUint32(5, readSeq, false)
  return bytes
}

const doneNotification = (status: number, nextSeq: number): Uint8Array => {
  const bytes = new Uint8Array(10)
  bytes[0] = 0x04
  bytes[1] = status
  new DataView(bytes.buffer).setUint32(6, nextSeq, false)
  return bytes
}

const dataNotification = (payload: Uint8Array): Uint8Array => Uint8Array.from([0x03, ...payload])

interface Harness {
  drain: RingDrain
  written: Uint8Array[]
  persisted: DrainedChunk[]
  emit: (bytes: Uint8Array) => void
  fireTimeouts: () => void
  setPersistError: (error: Error | null) => void
  setWriteError: (match: number, error: Error) => void
}

const harness = (
  over: {
    status?: Uint8Array | null
    autoRespond?: (written: Uint8Array, emit: (b: Uint8Array) => void) => void
    /** Every wait elapses immediately, exercising the give-up paths. */
    instantTimeouts?: boolean
    shouldStop?: () => boolean
    chunkSeconds?: number
    frameLengthBytes?: number
  } = {}
): Harness => {
  const written: Uint8Array[] = []
  const persisted: DrainedChunk[] = []
  let listener: ((bytes: Uint8Array) => void) | null = null
  let persistError: Error | null = null
  let writeErrorAt: { match: number; error: Error } | null = null
  const sleepers: Array<() => void> = []

  const emit = (bytes: Uint8Array): void => listener?.(bytes)

  const transport: StorageTransport = {
    writeCommand: async (bytes) => {
      written.push(bytes)
      if (writeErrorAt !== null && bytes[0] === writeErrorAt.match) throw writeErrorAt.error
      over.autoRespond?.(bytes, emit)
    },
    readStatus: async () => {
      if (over.status === null) throw new Error('no status characteristic')
      return over.status ?? statusBytes()
    },
    subscribe: (cb) => {
      listener = cb
      return () => {
        listener = null
      }
    },
    sleep: (_ms, signal) =>
      new Promise((resolve) => {
        if (signal.aborted) {
          resolve('aborted')
          return
        }
        if (over.instantTimeouts === true) {
          setTimeout(() => resolve('elapsed'), 0)
          return
        }
        sleepers.push(() => resolve('elapsed'))
        signal.addEventListener('abort', () => resolve('aborted'), { once: true })
      }),
    now: () => EPOCH * 1000
  }

  const sink: DrainSink = {
    persist: async (chunk) => {
      if (persistError !== null) throw persistError
      persisted.push(chunk)
    }
  }

  return {
    drain: new RingDrain({
      transport,
      sink,
      framesPerSecond: FRAMES_PER_SECOND,
      shouldStop: over.shouldStop,
      chunkSeconds: over.chunkSeconds,
      frameLengthBytes: over.frameLengthBytes
    }),
    written,
    persisted,
    emit,
    fireTimeouts: () => {
      for (const wake of sleepers.splice(0)) wake()
    },
    setPersistError: (error) => {
      persistError = error
    },
    setWriteError: (match, error) => {
      writeErrorAt = { match, error }
    }
  }
}

/** Responds to a read command with one record and a successful done. */
const respondWithRecord =
  (nextSeq: number, epoch = EPOCH) =>
  (written: Uint8Array, emit: (b: Uint8Array) => void): void => {
    if (written[0] === 0x10) {
      emit(infoNotification(7))
      return
    }
    if (written[0] !== 0x11) return
    emit(
      dataNotification(
        ringRecord(epoch, [
          [1, 2, 3],
          [4, 5, 6]
        ])
      )
    )
    emit(doneNotification(0, nextSeq))
  }

describe('RingDrain', () => {
  it('reads records, stores them, then advances the device pointer', async () => {
    const h = harness({ autoRespond: respondWithRecord(99) })
    const result = await h.drain.drain()

    expect(result).toMatchObject({ kind: 'drained', records: 1, chunks: 1, advancedTo: 99n })
    expect(h.persisted.length).toBe(1)
    expect(h.persisted[0].frames.map((f) => Array.from(f))).toEqual([
      [1, 2, 3],
      [4, 5, 6]
    ])
    expect(h.persisted[0].startEpochSeconds).toBe(EPOCH)

    // The order is the point: stop, info, read, then advance LAST.
    const opcodes = h.written.map((w) => w[0])
    expect(opcodes).toEqual([0x03, 0x10, 0x11, 0x12])
  })

  it('resumes from the sequence the device reports, not from zero', async () => {
    const h = harness({ autoRespond: respondWithRecord(50) })
    await h.drain.drain()
    const read = h.written.find((w) => w[0] === 0x11)!
    // read_seq 7 came from the info notification.
    expect(Array.from(read.subarray(1))).toEqual([0, 0, 0, 0, 0, 0, 0, 7])
  })

  it('does not advance when the transfer reports failure', async () => {
    const h = harness({
      autoRespond: (written, emit) => {
        if (written[0] !== 0x11) return
        emit(dataNotification(ringRecord(EPOCH, [[1, 2]])))
        emit(doneNotification(9, 123))
      }
    })
    const result = await h.drain.drain()
    expect(result.kind).toBe('incomplete')
    // The device still holds the audio, so the next attempt re-reads it.
    expect(h.written.some((w) => w[0] === 0x12)).toBe(false)
    expect(h.persisted).toEqual([])
  })

  it('does not advance when storing fails', async () => {
    const h = harness({ autoRespond: respondWithRecord(99) })
    h.setPersistError(new Error('disk full'))
    const result = await h.drain.drain()

    expect(result).toMatchObject({ kind: 'incomplete' })
    expect((result as { reason: string }).reason).toContain('disk full')
    // Advancing here would tell the device to reuse space holding audio that
    // was never saved.
    expect(h.written.some((w) => w[0] === 0x12)).toBe(false)
  })

  it('reports incomplete when the advance itself fails, with the audio kept', async () => {
    const h = harness({ autoRespond: respondWithRecord(99) })
    h.setWriteError(0x12, new Error('write failed'))
    const result = await h.drain.drain()

    expect(result.kind).toBe('incomplete')
    // The audio IS stored; only the pointer did not move, so the next drain
    // re-reads it. Duplicated work, never lost audio.
    expect(h.persisted.length).toBe(1)
  })

  it('gives up when the device sends nothing', async () => {
    const h = harness({ instantTimeouts: true })
    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'incomplete', reason: 'device sent no data' })
    expect(h.written.some((w) => w[0] === 0x12)).toBe(false)
  })

  it('gives up when data starts but the transfer never completes', async () => {
    const h = harness({
      instantTimeouts: true,
      autoRespond: (written, emit) => {
        // Data arrives, then the device goes quiet without a done.
        if (written[0] === 0x11) emit(dataNotification(ringRecord(EPOCH, [[1, 2]])))
      }
    })
    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'incomplete', reason: 'transfer timed out' })
    // Read but never committed, so the device keeps it.
    expect(h.written.some((w) => w[0] === 0x12)).toBe(false)
    expect(h.persisted).toEqual([])
  })

  it('does nothing when the ring is empty', async () => {
    const h = harness({ status: statusBytes({ unread: 0 }) })
    expect(await h.drain.drain()).toEqual({ kind: 'idle', reason: 'nothing-to-read' })
    expect(h.written).toEqual([])
  })

  it('reports unsupported when the status characteristic is not there', async () => {
    const h = harness({ status: null })
    expect(await h.drain.drain()).toEqual({ kind: 'idle', reason: 'unsupported' })
  })

  it('reassembles records split across data notifications', async () => {
    const record = ringRecord(EPOCH, [[7, 7, 7]])
    const h = harness({
      autoRespond: (written, emit) => {
        if (written[0] !== 0x11) return
        // The transport does not align notifications to records.
        emit(dataNotification(record.subarray(0, 200)))
        emit(dataNotification(record.subarray(200)))
        emit(doneNotification(0, 5))
      }
    })
    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'drained', records: 1 })
    expect(h.persisted[0].frames.map((f) => Array.from(f))).toEqual([[7, 7, 7]])
  })

  it('places the audio behind the drain time when the device clock is unreliable', async () => {
    // 1000 unread packets of 440 payload bytes, 81 bytes per stored frame at 50
    // frames a second, is about 108 seconds of audio ending about now.
    const h = harness({
      status: statusBytes({ rtc: 0, unread: 1000 }),
      autoRespond: respondWithRecord(1, 946_684_800) // a clearly wrong device time
    })
    await h.drain.drain()
    // A wrong capture time would put the recording outside the recovery window
    // and get it permanently refused, and a capture time of exactly now would
    // date every recovered second to the moment it was recovered.
    expect(h.persisted[0].startEpochSeconds).toBe(EPOCH - 108)
  })

  it('advances the capture time from record to record when the clock is unreliable', async () => {
    // Two records of 50 three-byte frames, one second per chunk at 50 frames a
    // second, so each record is exactly one chunk.
    const record = ringRecord(
      0,
      Array.from({ length: 50 }, () => [1, 2, 3])
    )
    const h = harness({
      status: statusBytes({ rtc: 0, unread: 2 }),
      chunkSeconds: 1,
      autoRespond: (written, emit) => {
        if (written[0] !== 0x11) return
        emit(dataNotification(record))
        emit(dataNotification(record))
        emit(doneNotification(0, 2))
      }
    })
    await h.drain.drain()
    // Recordings are identified by their start, so stamping both records with
    // the same drain time would make the second look like a duplicate of the
    // first and lose it.
    expect(h.persisted.map((c) => c.startEpochSeconds)).toEqual([EPOCH, EPOCH + 1])
  })

  it('a cancelled drain keeps the audio on the device', async () => {
    let stop = false
    const h = harness({
      shouldStop: () => stop,
      autoRespond: (written, emit) => {
        if (written[0] !== 0x11) return
        stop = true
        emit(dataNotification(ringRecord(EPOCH, [[1, 2, 3]])))
        emit(doneNotification(0, 9))
      }
    })
    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'incomplete', reason: 'cancelled' })
    // Nothing was stored and the read pointer never moved, so the next attempt
    // reads the same records.
    expect(h.persisted).toEqual([])
    expect(h.written.some((w) => w[0] === 0x12)).toBe(false)
    // The device is told to stop rather than left streaming into nothing.
    expect(h.written[h.written.length - 1][0]).toBe(0x03)
  })

  it('stops an interrupted transfer before starting a new one', async () => {
    const h = harness({ autoRespond: respondWithRecord(1) })
    await h.drain.drain()
    expect(h.written[0][0]).toBe(0x03)
  })

  it('a rejected command ends the drain without advancing', async () => {
    const h = harness({
      autoRespond: (written, emit) => {
        if (written[0] === 0x11) emit(Uint8Array.from([0x01, 4]))
      }
    })
    const result = await h.drain.drain()
    expect(result.kind).toBe('incomplete')
    expect(h.written.some((w) => w[0] === 0x12)).toBe(false)
  })
})
