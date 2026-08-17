import { describe, it, expect } from 'vitest'
import { FileDrain } from './fileDrain'
import type { DrainSink, StorageTransport } from './ringDrain'
import type { DrainedChunk } from './storageChunker'

const FRAMES_PER_SECOND = 50
const EPOCH = 1_723_800_000

/** `[count u8]` then `[timestamp u32 BE][size u32 BE]` per file. */
const listing = (files: Array<{ epoch: number; size: number }>): Uint8Array => {
  const bytes = new Uint8Array(1 + files.length * 8)
  bytes[0] = files.length
  const view = new DataView(bytes.buffer)
  files.forEach((file, i) => {
    view.setUint32(1 + i * 8, file.epoch, false)
    view.setUint32(5 + i * 8, file.size, false)
  })
  return bytes
}

/** `[timestamp u32 BE][packed audio]` */
const fileData = (epoch: number, frames: number[][]): Uint8Array => {
  const packed: number[] = []
  for (const frame of frames) packed.push(frame.length, ...frame)
  const bytes = new Uint8Array(4 + packed.length)
  new DataView(bytes.buffer).setUint32(0, epoch, false)
  bytes.set(packed, 4)
  return bytes
}

interface Script {
  onList?: (emit: (b: Uint8Array) => void) => void
  onRead?: (index: number, emit: (b: Uint8Array) => void) => void
  onDelete?: (index: number) => void | 'fail'
}

const harness = (
  script: Script,
  over: { shouldStop?: () => boolean; chunkSeconds?: number } = {}
): {
  drain: FileDrain
  persisted: DrainedChunk[]
  deletes: number[]
  reads: number[]
  setPersistError: (e: Error | null) => void
} => {
  const persisted: DrainedChunk[] = []
  const deletes: number[] = []
  const reads: number[] = []
  let listener: ((bytes: Uint8Array) => void) | null = null
  let persistError: Error | null = null
  const emit = (bytes: Uint8Array): void => listener?.(bytes)

  const transport: StorageTransport = {
    writeCommand: async (bytes) => {
      if (bytes[0] === 0x10) {
        script.onList?.(emit)
        return
      }
      if (bytes[0] === 0x11) {
        reads.push(bytes[1])
        script.onRead?.(bytes[1], emit)
        return
      }
      if (bytes[0] === 0x12) {
        if (script.onDelete?.(bytes[1]) === 'fail') throw new Error('delete failed')
        deletes.push(bytes[1])
      }
    },
    readStatus: async () => new Uint8Array(0),
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
        // Settle waits resolve immediately; transfer waits only when the test
        // is exercising a give-up path.
        setTimeout(() => resolve('elapsed'), 0)
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
    drain: new FileDrain({
      transport,
      sink,
      framesPerSecond: FRAMES_PER_SECOND,
      shouldStop: over.shouldStop,
      chunkSeconds: over.chunkSeconds
    }),
    persisted,
    deletes,
    reads,
    setPersistError: (e) => {
      persistError = e
    }
  }
}

const completeStatus = Uint8Array.from([100])

describe('FileDrain', () => {
  it('reads every file, stores it, then deletes highest index first', async () => {
    const h = harness({
      onList: (emit) =>
        emit(
          listing([
            { epoch: EPOCH, size: 400 },
            { epoch: EPOCH + 600, size: 400 },
            { epoch: EPOCH + 1200, size: 400 }
          ])
        ),
      onRead: (index, emit) => {
        emit(fileData(EPOCH + index * 600, [[index + 1, index + 1]]))
        emit(completeStatus)
      }
    })

    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'drained', files: 3, chunks: 3, deleted: 3 })
    expect(h.reads).toEqual([0, 1, 2])
    // Deleting 0 first would shift 1 and 2 down and delete the wrong files.
    expect(h.deletes).toEqual([2, 1, 0])
    expect(h.persisted.map((c) => c.startEpochSeconds)).toEqual([EPOCH, EPOCH + 600, EPOCH + 1200])
  })

  it('skips empty files', async () => {
    const h = harness({
      onList: (emit) => emit(listing([{ epoch: EPOCH, size: 0 }]))
    })
    expect(await h.drain.drain()).toEqual({ kind: 'idle', reason: 'nothing-to-read' })
    expect(h.reads).toEqual([])
  })

  it('reports nothing to read for an empty listing', async () => {
    const h = harness({ onList: (emit) => emit(listing([])) })
    expect(await h.drain.drain()).toEqual({ kind: 'idle', reason: 'nothing-to-read' })
  })

  it('reports unsupported when the device never answers the listing', async () => {
    const h = harness({})
    expect(await h.drain.drain()).toEqual({ kind: 'idle', reason: 'unsupported' })
  })

  it('never deletes a file whose audio could not be stored', async () => {
    const h = harness({
      onList: (emit) => emit(listing([{ epoch: EPOCH, size: 400 }])),
      onRead: (_index, emit) => {
        emit(fileData(EPOCH, [[1, 2]]))
        emit(completeStatus)
      }
    })
    h.setPersistError(new Error('disk full'))

    const result = await h.drain.drain()
    expect(result.kind).toBe('incomplete')
    // The device keeps the only copy.
    expect(h.deletes).toEqual([])
  })

  it('keeps the files it could not read and deletes only the stored ones', async () => {
    const h = harness({
      onList: (emit) =>
        emit(
          listing([
            { epoch: EPOCH, size: 400 },
            { epoch: EPOCH + 600, size: 400 }
          ])
        ),
      onRead: (index, emit) => {
        if (index === 0) {
          emit(fileData(EPOCH, [[1, 2]]))
          emit(completeStatus)
          return
        }
        // The second file fails mid-transfer.
        emit(Uint8Array.from([3]))
      }
    })

    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'incomplete', files: 1, deleted: 1 })
    // Only the file that was actually stored is removed.
    expect(h.deletes).toEqual([0])
    expect(h.persisted.length).toBe(1)
  })

  it('treats an empty-file reply as a clean ending, not a failure', async () => {
    const h = harness({
      onList: (emit) => emit(listing([{ epoch: EPOCH, size: 400 }])),
      onRead: (_index, emit) => emit(Uint8Array.from([4]))
    })
    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'drained', files: 1, chunks: 0 })
    expect(h.deletes).toEqual([0])
  })

  it('falls back to the listing time when a record carries no timestamp', async () => {
    const h = harness({
      onList: (emit) => emit(listing([{ epoch: EPOCH, size: 400 }])),
      onRead: (_index, emit) => {
        emit(fileData(0, [[9]]))
        emit(completeStatus)
      }
    })
    await h.drain.drain()
    // A zero timestamp would otherwise date the recording to 1970 and get it
    // permanently refused as outside the recovery window.
    expect(h.persisted[0].startEpochSeconds).toBe(EPOCH)
  })

  it('stops a stale transfer before listing', async () => {
    const commands: number[] = []
    const h = harness({
      onList: (emit) => {
        commands.push(0x10)
        emit(listing([]))
      }
    })
    await h.drain.drain()
    expect(commands).toEqual([0x10])
  })

  it('a cancelled pass keeps what it stored and leaves the rest on the device', async () => {
    let stop = false
    const h = harness(
      {
        onList: (emit) =>
          emit(
            listing([
              { epoch: EPOCH, size: 400 },
              { epoch: EPOCH + 600, size: 400 },
              { epoch: EPOCH + 1200, size: 400 }
            ])
          ),
        onRead: (index, emit) => {
          emit(fileData(EPOCH + index * 600, [[1]]))
          emit(completeStatus)
          stop = true
        }
      },
      { shouldStop: () => stop }
    )

    const result = await h.drain.drain()
    expect(result).toMatchObject({ kind: 'incomplete', reason: 'cancelled', files: 1 })
    // The first file is stored, so deleting it is right; the other two were
    // never read and must survive.
    expect(h.reads).toEqual([0])
    expect(h.deletes).toEqual([0])
    expect(h.persisted.length).toBe(1)
  })

  it('advances the capture time across the untimed payloads of one file', async () => {
    const payload = fileData(
      0,
      Array.from({ length: 50 }, () => [7])
    )
    const h = harness(
      {
        onList: (emit) => emit(listing([{ epoch: EPOCH, size: 4000 }])),
        onRead: (_index, emit) => {
          // Three payloads of 50 frames, one second per chunk at 50 frames a
          // second, all carrying the same (absent) timestamp.
          emit(payload)
          emit(payload)
          emit(payload)
          emit(completeStatus)
        }
      },
      { chunkSeconds: 1 }
    )
    await h.drain.drain()
    // Reusing the file's listing time for all three would give three chunks the
    // same identity and keep only the first.
    expect(h.persisted.map((c) => c.startEpochSeconds)).toEqual([EPOCH, EPOCH + 1, EPOCH + 2])
  })

  it('a delete that fails leaves the rest for the next pass', async () => {
    const h = harness({
      onList: (emit) =>
        emit(
          listing([
            { epoch: EPOCH, size: 400 },
            { epoch: EPOCH + 600, size: 400 }
          ])
        ),
      onRead: (index, emit) => {
        emit(fileData(EPOCH + index * 600, [[1]]))
        emit(completeStatus)
      },
      onDelete: (index) => (index === 1 ? 'fail' : undefined)
    })
    const result = await h.drain.drain()
    // Highest index is attempted first and fails, so nothing is deleted; the
    // audio is stored, so the next pass just re-reads it.
    expect(result).toMatchObject({ kind: 'drained', deleted: 0 })
    expect(h.persisted.length).toBe(2)
  })
})
