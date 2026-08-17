import { describe, it, expect } from 'vitest'
import { StorageDrainService, encodeFrames, createWalDrainSink } from './storageDrainService'
import { STORAGE_UUIDS } from '../protocol/uuids'
import type { DeviceConnection } from '../connections/deviceConnection'
import type { DrainSink } from './ringDrain'
import type { DrainedChunk } from './storageChunker'
import { RING_RECORD_BYTES, PAYLOAD_BYTES as RING_PAYLOAD_BYTES } from './storageProtocol'

const EPOCH = 1_723_800_000

const ringStatus = (unread: number): Uint8Array => {
  const bytes = new Uint8Array(16)
  const view = new DataView(bytes.buffer)
  view.setUint32(4, unread, true)
  view.setUint32(12, 1, true)
  return bytes
}

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

const fileListing = (files: Array<{ epoch: number; size: number }>): Uint8Array => {
  const bytes = new Uint8Array(1 + files.length * 8)
  bytes[0] = files.length
  const view = new DataView(bytes.buffer)
  files.forEach((f, i) => {
    view.setUint32(1 + i * 8, f.epoch, false)
    view.setUint32(5 + i * 8, f.size, false)
  })
  return bytes
}

interface Script {
  status?: Uint8Array | 'throw'
  onCommand?: (bytes: Uint8Array, emit: (b: Uint8Array) => void) => void
}

const harness = (
  script: Script
): {
  service: StorageDrainService
  persisted: DrainedChunk[]
  written: Uint8Array[]
} => {
  const persisted: DrainedChunk[] = []
  const written: Uint8Array[] = []
  let listener: ((bytes: Uint8Array) => void) | null = null
  const emit = (bytes: Uint8Array): void => listener?.(bytes)

  const connection = {
    transport: {
      writeCharacteristic: async (args: {
        serviceUuid: string
        characteristicUuid: string
        data: Uint8Array
      }) => {
        expect(args.serviceUuid).toBe(STORAGE_UUIDS.service)
        expect(args.characteristicUuid).toBe(STORAGE_UUIDS.dataStream)
        written.push(args.data)
        script.onCommand?.(args.data, emit)
      },
      readCharacteristic: async (_service: string, characteristic: string) => {
        expect(characteristic).toBe(STORAGE_UUIDS.readControl)
        if (script.status === 'throw') throw new Error('no characteristic')
        return script.status ?? ringStatus(0)
      },
      subscribeCharacteristic: (
        _service: string,
        _characteristic: string,
        subscriber: { onData: (d: Uint8Array) => void; onFinish: () => void }
      ) => {
        listener = subscriber.onData
        return {
          cancel: () => {
            listener = null
          }
        }
      }
    }
  } as unknown as DeviceConnection

  const sink: DrainSink = {
    persist: async (chunk) => {
      persisted.push(chunk)
    }
  }

  const service = new StorageDrainService({
    connection,
    sink,
    codec: 'opus',
    sleep: async () => 'elapsed'
  })
  return { service, persisted, written }
}

describe('StorageDrainService', () => {
  it('drains the ring when the device speaks it', async () => {
    const h = harness({
      status: ringStatus(2),
      onCommand: (bytes, emit) => {
        if (bytes[0] !== 0x11) return
        emit(Uint8Array.from([0x03, ...ringRecord(EPOCH, [[1, 2, 3]])]))
        const done = new Uint8Array(10)
        done[0] = 0x04
        done[9] = 5
        emit(done)
      }
    })

    const result = await h.service.drainOnce()
    expect(result).toMatchObject({ kind: 'drained', protocol: 'ring', chunks: 1 })
    expect(h.persisted[0].frames.map((f) => Array.from(f))).toEqual([[1, 2, 3]])
  })

  it('falls through to the file listing when the ring reports unsupported', async () => {
    const h = harness({
      // No status characteristic at all is the older firmware shape.
      status: 'throw',
      onCommand: (bytes, emit) => {
        if (bytes[0] === 0x10) {
          emit(fileListing([{ epoch: EPOCH, size: 400 }]))
          return
        }
        if (bytes[0] === 0x11) {
          const data = new Uint8Array(4 + 2)
          new DataView(data.buffer).setUint32(0, EPOCH, false)
          data[4] = 1
          data[5] = 9
          emit(data)
          emit(Uint8Array.from([100]))
        }
      }
    })

    const result = await h.service.drainOnce()
    expect(result).toMatchObject({ kind: 'drained', protocol: 'files', chunks: 1 })
  })

  it('does not probe the file protocol when the ring is simply empty', async () => {
    const h = harness({ status: ringStatus(0) })
    const result = await h.service.drainOnce()
    expect(result).toEqual({ kind: 'idle', reason: 'nothing-to-read' })
    // Probing on would send commands to a device with nothing to give.
    expect(h.written).toEqual([])
  })

  it('reports unsupported when neither protocol answers', async () => {
    const h = harness({ status: 'throw' })
    expect(await h.service.drainOnce()).toEqual({ kind: 'unsupported' })
  })

  it('refuses a second concurrent drain', async () => {
    const h = harness({ status: ringStatus(0) })
    const [first, second] = await Promise.all([h.service.drainOnce(), h.service.drainOnce()])
    // Two drains would interleave commands on the same characteristic.
    const refused = [first, second].filter(
      (r) => r.kind === 'idle' && r.reason === 'already-draining'
    )
    expect(refused.length).toBe(1)
  })
})

describe('StorageDrainService.probe', () => {
  it('reports what the ring holds without reading any of it', async () => {
    const h = harness({ status: ringStatus(1000) })
    const probe = await h.service.probe()
    expect(probe).toEqual({
      protocol: 'ring',
      items: 1000,
      bytes: 1000 * RING_PAYLOAD_BYTES,
      // 440000 bytes at 81 bytes a frame and 100 frames a second.
      estimatedSeconds: Math.round((1000 * RING_PAYLOAD_BYTES) / (81 * 100))
    })
    // Probing must not start a transfer.
    expect(h.written).toEqual([])
  })

  it('reports nothing when the ring is empty', async () => {
    const h = harness({ status: ringStatus(0) })
    expect(await h.service.probe()).toBeNull()
    expect(h.written).toEqual([])
  })

  it('falls through to the file listing and sums the stored files', async () => {
    const h = harness({
      status: 'throw',
      onCommand: (bytes, emit) => {
        if (bytes[0] !== 0x10) return
        emit(
          fileListing([
            { epoch: EPOCH, size: 400 },
            { epoch: EPOCH + 600, size: 0 },
            { epoch: EPOCH + 1200, size: 600 }
          ])
        )
      }
    })
    const probe = await h.service.probe()
    // The empty file is not something the user can recover.
    expect(probe).toMatchObject({ protocol: 'files', items: 2, bytes: 1000 })
  })

  it('reports nothing when the device speaks neither protocol', async () => {
    const h = harness({ status: 'throw' })
    expect(await h.service.probe()).toBeNull()
  })

  it('refuses to probe while a drain is running', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const h = harness({
      status: ringStatus(2),
      onCommand: (bytes, emit) => {
        if (bytes[0] !== 0x11) return
        void gate.then(() => {
          emit(Uint8Array.from([0x03, ...ringRecord(EPOCH, [[1, 2, 3]])]))
          const done = new Uint8Array(10)
          done[0] = 0x04
          done[9] = 5
          emit(done)
        })
      }
    })
    const draining = h.service.drainOnce()
    // A probe mid-transfer would interleave its commands with the transfer.
    expect(await h.service.probe()).toBeNull()
    release()
    await draining
  })
})

describe('encodeFrames', () => {
  it('writes each frame with a little-endian length prefix', () => {
    const encoded = encodeFrames([Uint8Array.from([1, 2, 3]), Uint8Array.from([4])])
    expect(Array.from(encoded)).toEqual([3, 0, 0, 0, 1, 2, 3, 1, 0, 0, 0, 4])
  })

  it('encodes nothing for no frames', () => {
    expect(encodeFrames([]).byteLength).toBe(0)
  })
})

describe('createWalDrainSink', () => {
  const chunk = {
    frames: [Uint8Array.from([1]), Uint8Array.from([2])],
    startEpochSeconds: EPOCH,
    seconds: 12,
    byteLength: 2
  }

  it('hands the encoded bytes and the capture start to the persister', async () => {
    const calls: Array<{ startEpochSeconds: number; seconds: number; frameCount: number }> = []
    const sink = createWalDrainSink(async (args) => {
      calls.push({
        startEpochSeconds: args.startEpochSeconds,
        seconds: args.seconds,
        frameCount: args.frameCount
      })
      return 'stored'
    })
    await sink.persist(chunk)
    expect(calls).toEqual([{ startEpochSeconds: EPOCH, seconds: 12, frameCount: 2 }])
  })

  it('throws when the recording could not be stored', async () => {
    const sink = createWalDrainSink(async () => 'failed')
    // The drains read a throw as "not stored", which is what keeps the audio on
    // the device instead of deleting it.
    await expect(sink.persist(chunk)).rejects.toThrow()
  })

  it('accepts a duplicate as stored', async () => {
    const sink = createWalDrainSink(async () => 'duplicate')
    // An interrupted transfer re-reads records it already delivered; the
    // recording is already safe, so the device copy is free to go.
    await expect(sink.persist(chunk)).resolves.toBeUndefined()
  })
})
