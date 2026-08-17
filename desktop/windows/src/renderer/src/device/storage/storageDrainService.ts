/**
 * Picks the storage protocol a connected device speaks and drains it into the
 * write-ahead log, where the existing sync engine uploads it like any other
 * recording the socket could not take.
 *
 * Probe order matches the Flutter orchestration: ring buffer first (current
 * firmware), then the multi-file listing. A device that answers neither is left
 * alone rather than guessed at, because a wrong command on the storage
 * characteristic can abort a transfer that is already in flight.
 */

import { STORAGE_UUIDS } from '../protocol/uuids'
import { codecFramesPerSecond, type BleAudioCodec } from '../protocol/deviceTypes'
import type { DeviceConnection } from '../connections/deviceConnection'
import { RingDrain, type DrainSink, type StorageTransport } from './ringDrain'
import { FileDrain } from './fileDrain'
import type { DrainedChunk } from './storageChunker'

export type DrainOutcome =
  | { kind: 'idle'; reason: string }
  | { kind: 'drained'; chunks: number; protocol: 'ring' | 'files' }
  | { kind: 'incomplete'; reason: string; chunks: number; protocol: 'ring' | 'files' }
  | { kind: 'unsupported' }

export interface StorageDrainOptions {
  connection: DeviceConnection
  sink: DrainSink
  codec: BleAudioCodec
  sleep: (ms: number, signal: AbortSignal) => Promise<'elapsed' | 'aborted'>
  now?: () => number
  onProgress?: (message: string) => void
}

/**
 * Adapts a device connection to the raw storage characteristics: commands and
 * data share `30295781`, status is read from `30295782`.
 */
export function createStorageTransport(
  connection: DeviceConnection,
  sleep: StorageDrainOptions['sleep'],
  now: () => number = () => Date.now()
): StorageTransport {
  return {
    writeCommand: async (bytes) => {
      await connection.transport.writeCharacteristic({
        serviceUuid: STORAGE_UUIDS.service,
        characteristicUuid: STORAGE_UUIDS.dataStream,
        data: bytes,
        withResponse: true
      })
    },
    readStatus: async () =>
      connection.transport.readCharacteristic(STORAGE_UUIDS.service, STORAGE_UUIDS.readControl),
    subscribe: (onNotification) => {
      const subscription = connection.transport.subscribeCharacteristic(
        STORAGE_UUIDS.service,
        STORAGE_UUIDS.dataStream,
        {
          onData: (data) => onNotification(data),
          onFinish: () => undefined
        }
      )
      return () => subscription.cancel()
    },
    sleep,
    now
  }
}

export class StorageDrainService {
  private running = false

  constructor(private readonly options: StorageDrainOptions) {}

  get isRunning(): boolean {
    return this.running
  }

  /**
   * Drains once. Concurrent calls are refused: two drains would issue
   * interleaved commands on the same characteristic and corrupt both.
   */
  async drainOnce(): Promise<DrainOutcome> {
    if (this.running) return { kind: 'idle', reason: 'already-draining' }
    this.running = true
    try {
      const framesPerSecond = codecFramesPerSecond(this.options.codec)
      const transport = createStorageTransport(
        this.options.connection,
        this.options.sleep,
        this.options.now
      )
      const sink = this.options.sink

      const ring = new RingDrain({
        transport,
        sink,
        framesPerSecond,
        onProgress: (p) =>
          this.options.onProgress?.(`Recovering ${p.records} recorded packets from your device`)
      })
      const ringStatus = await ring.status()
      if (ringStatus !== null) {
        const result = await ring.drain()
        if (result.kind === 'drained') {
          return { kind: 'drained', chunks: result.chunks, protocol: 'ring' }
        }
        if (result.kind === 'incomplete') {
          return {
            kind: 'incomplete',
            reason: result.reason,
            chunks: result.chunks,
            protocol: 'ring'
          }
        }
        // The ring answered but had nothing; no reason to probe further.
        if (result.reason === 'nothing-to-read') return { kind: 'idle', reason: result.reason }
      }

      const files = new FileDrain({
        transport,
        sink,
        framesPerSecond,
        onProgress: (p) =>
          this.options.onProgress?.(`Recovering recording ${p.file} of ${p.ofFiles}`)
      })
      const result = await files.drain()
      switch (result.kind) {
        case 'drained':
          return { kind: 'drained', chunks: result.chunks, protocol: 'files' }
        case 'incomplete':
          return {
            kind: 'incomplete',
            reason: result.reason,
            chunks: result.chunks,
            protocol: 'files'
          }
        case 'idle':
          return result.reason === 'unsupported'
            ? { kind: 'unsupported' }
            : { kind: 'idle', reason: result.reason }
      }
    } finally {
      this.running = false
    }
  }
}

/**
 * Builds the sink that turns drained chunks into write-ahead-log entries. The
 * frames are written in the same `[length u32 LE][frame]` layout the device
 * families use, which is what the upload expects.
 */
export function createWalDrainSink(
  persist: (args: {
    bytes: Uint8Array
    startEpochSeconds: number
    seconds: number
    frameCount: number
  }) => Promise<void>
): DrainSink {
  return {
    persist: async (chunk: DrainedChunk) => {
      await persist({
        bytes: encodeFrames(chunk.frames),
        startEpochSeconds: chunk.startEpochSeconds,
        seconds: chunk.seconds,
        frameCount: chunk.frames.length
      })
    }
  }
}

/** `[frame length u32 LE][frame bytes]` repeated, matching the stored format. */
export function encodeFrames(frames: Uint8Array[]): Uint8Array {
  const total = frames.reduce((sum, frame) => sum + 4 + frame.byteLength, 0)
  const out = new Uint8Array(total)
  const view = new DataView(out.buffer)
  let offset = 0
  for (const frame of frames) {
    view.setUint32(offset, frame.byteLength, true)
    out.set(frame, offset + 4)
    offset += 4 + frame.byteLength
  }
  return out
}
