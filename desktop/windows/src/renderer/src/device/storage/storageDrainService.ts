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
import {
  codecFrameLengthInBytes,
  codecFramesPerSecond,
  type BleAudioCodec
} from '../protocol/deviceTypes'
import type { DeviceConnection } from '../connections/deviceConnection'
import { RingDrain, type DrainSink, type StorageTransport } from './ringDrain'
import { FileDrain } from './fileDrain'
import { PAYLOAD_BYTES } from './storageProtocol'
import type { DrainedChunk } from './storageChunker'

export type DrainOutcome =
  | { kind: 'idle'; reason: string }
  | { kind: 'drained'; chunks: number; protocol: 'ring' | 'files' }
  | { kind: 'incomplete'; reason: string; chunks: number; protocol: 'ring' | 'files' }
  | { kind: 'unsupported' }

/** What a connected device is holding, without transferring any of it. */
export interface StorageProbe {
  protocol: 'ring' | 'files'
  /** Ring packets, or stored files. */
  items: number
  bytes: number
  /** Estimated from the codec's nominal frame length, so it is a size hint for
   *  the UI and never a value anything decides on. */
  estimatedSeconds: number
}

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
  private stopRequested = false

  constructor(private readonly options: StorageDrainOptions) {}

  get isRunning(): boolean {
    return this.running
  }

  /** Stops the transfer in progress at the next safe point. */
  cancel(): void {
    this.stopRequested = true
  }

  /**
   * Reports what the device is holding without reading any of it, so the UI can
   * offer recovery instead of starting a transfer that may run for minutes.
   *
   * Null means nothing to recover: either the device holds no stored audio or it
   * speaks neither protocol.
   */
  async probe(): Promise<StorageProbe | null> {
    // A probe during a transfer would interleave commands with it.
    if (this.running) return null
    this.running = true
    try {
      const transport = this.transport()
      const framesPerSecond = codecFramesPerSecond(this.options.codec)
      const bytesPerSecond = (codecFrameLengthInBytes(this.options.codec) + 1) * framesPerSecond

      const ringStatus = await new RingDrain({
        transport,
        sink: this.options.sink,
        framesPerSecond
      }).status()
      if (ringStatus !== null) {
        if (ringStatus.unreadPackets === 0) return null
        const bytes = ringStatus.unreadPackets * PAYLOAD_BYTES
        return {
          protocol: 'ring',
          items: ringStatus.unreadPackets,
          bytes,
          estimatedSeconds: Math.round(bytes / bytesPerSecond)
        }
      }

      const files = await new FileDrain({
        transport,
        sink: this.options.sink,
        framesPerSecond
      }).listFiles()
      if (files === null) return null
      const withAudio = files.filter((file) => file.sizeBytes > 0)
      if (withAudio.length === 0) return null
      const bytes = withAudio.reduce((sum, file) => sum + file.sizeBytes, 0)
      return {
        protocol: 'files',
        items: withAudio.length,
        bytes,
        estimatedSeconds: Math.round(bytes / bytesPerSecond)
      }
    } catch {
      return null
    } finally {
      this.running = false
    }
  }

  /**
   * Drains once. Concurrent calls are refused: two drains would issue
   * interleaved commands on the same characteristic and corrupt both.
   */
  async drainOnce(): Promise<DrainOutcome> {
    if (this.running) return { kind: 'idle', reason: 'already-draining' }
    this.running = true
    this.stopRequested = false
    try {
      const framesPerSecond = codecFramesPerSecond(this.options.codec)
      const transport = this.transport()
      const sink = this.options.sink
      const shouldStop = (): boolean => this.stopRequested

      const ring = new RingDrain({
        transport,
        sink,
        framesPerSecond,
        shouldStop,
        frameLengthBytes: codecFrameLengthInBytes(this.options.codec),
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
        shouldStop,
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
      this.stopRequested = false
    }
  }

  private transport(): StorageTransport {
    return createStorageTransport(this.options.connection, this.options.sleep, this.options.now)
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
