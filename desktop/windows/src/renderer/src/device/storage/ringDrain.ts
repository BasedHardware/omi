/**
 * Drains the device ring buffer (firmware 3.0.20 and later).
 *
 * The invariant this module exists to protect: the device's read pointer is
 * only advanced after the transfer reported success AND every chunk was
 * durably stored. Advancing earlier tells the device the audio is safe when it
 * is not, and the ring will overwrite it. Any failure leaves the pointer where
 * it was, so the next attempt re-reads the same records.
 *
 * Ported from Flutter `ring_storage_sync.dart`.
 */

import {
  RingRecordReassembler,
  encodeRingAdvance,
  encodeRingInfo,
  encodeRingRead,
  encodeStorageStop,
  parseRingNotification,
  parseRingStatus,
  unpackPayload,
  type RingStatus
} from './storageProtocol'
import { StorageChunker, stampFrames, type DrainedChunk } from './storageChunker'

/** First data must arrive within this or the device is not responding. */
export const FIRST_DATA_TIMEOUT_MS = 5_000
/** A whole ring drain may not exceed this. */
export const DRAIN_TIMEOUT_MS = 30 * 60_000

export interface StorageTransport {
  /** Writes a command to the storage control characteristic. */
  writeCommand(bytes: Uint8Array): Promise<void>
  /** Reads the storage status characteristic. */
  readStatus(): Promise<Uint8Array>
  /** Subscribes to control-characteristic notifications; returns unsubscribe. */
  subscribe(onNotification: (bytes: Uint8Array) => void): () => void
  /** Injectable so tests drive timeouts without waiting. */
  sleep: (ms: number, signal: AbortSignal) => Promise<'elapsed' | 'aborted'>
  now: () => number
}

export interface DrainSink {
  /** Persists one chunk. Must only resolve once the audio is durable. */
  persist: (chunk: DrainedChunk) => Promise<void>
}

export interface RingDrainOptions {
  transport: StorageTransport
  sink: DrainSink
  framesPerSecond: number
  onProgress?: (progress: { records: number; chunks: number; bytes: number }) => void
}

export type RingDrainResult =
  | { kind: 'idle'; reason: 'nothing-to-read' | 'unsupported' }
  | { kind: 'drained'; records: number; chunks: number; advancedTo: bigint }
  /** Audio was read but not committed; the device still holds it. */
  | { kind: 'incomplete'; reason: string; records: number; chunks: number }

export class RingDrain {
  private readonly reassembler = new RingRecordReassembler()

  constructor(private readonly options: RingDrainOptions) {}

  /** Reads the status characteristic; null when this is not a ring firmware. */
  async status(): Promise<RingStatus | null> {
    try {
      return parseRingStatus(await this.options.transport.readStatus())
    } catch {
      return null
    }
  }

  async drain(): Promise<RingDrainResult> {
    const { transport, sink } = this.options
    const status = await this.status()
    if (status === null) return { kind: 'idle', reason: 'unsupported' }
    if (status.unreadPackets === 0) return { kind: 'idle', reason: 'nothing-to-read' }

    // Kill any transfer left in flight by an interrupted session before
    // starting: the device would otherwise interleave its records with ours.
    await transport.writeCommand(encodeStorageStop()).catch(() => undefined)

    const chunker = new StorageChunker({ framesPerSecond: this.options.framesPerSecond })
    const persisted: DrainedChunk[] = []
    let records = 0
    let bytes = 0
    let readSeq: bigint | null = null
    let doneSeq: bigint | null = null
    let failure: string | null = null
    let sawData = false

    const abort = new AbortController()
    let settle: () => void = () => undefined
    const finished = new Promise<void>((resolve) => {
      settle = resolve
    })

    const unsubscribe = transport.subscribe((raw) => {
      const notification = parseRingNotification(raw)
      if (notification === null) return
      switch (notification.kind) {
        case 'info':
          readSeq = notification.readSeq
          return
        case 'data': {
          sawData = true
          for (const record of this.reassembler.push(notification.bytes)) {
            records += 1
            bytes += record.payload.byteLength
            const { frames, timestamps } = unpackPayload(record.payload)
            const stamped = stampFrames(
              frames,
              // An unreliable device clock makes record times meaningless, so
              // the drain time is used instead of a wrong capture time.
              status.rtcValid ? record.epochSeconds : Math.floor(transport.now() / 1000),
              timestamps,
              this.options.framesPerSecond
            )
            for (const chunk of chunker.push(stamped)) persisted.push(chunk)
          }
          this.options.onProgress?.({ records, chunks: persisted.length, bytes })
          return
        }
        case 'done':
          if (!notification.ok) failure = `transfer reported status ${notification.status}`
          doneSeq = notification.nextSeq
          settle()
          return
        case 'ack':
          if (!notification.ok) {
            failure = `command rejected with status ${notification.status}`
            settle()
          }
          return
        default:
          return
      }
    })

    try {
      await transport.writeCommand(encodeRingInfo()).catch(() => undefined)
      const startSeq = readSeq ?? 0n
      await transport.writeCommand(encodeRingRead(startSeq))

      const timedOut = await this.waitFor(finished, abort, () => sawData)
      if (timedOut !== null) failure = timedOut
    } catch (error) {
      failure = error instanceof Error ? error.message : String(error)
    } finally {
      abort.abort()
      unsubscribe()
    }

    // Everything still buffered belongs to this transfer.
    for (const chunk of chunker.flush()) persisted.push(chunk)
    this.reassembler.reset()

    if (failure !== null || doneSeq === null) {
      // Read but not committed: the device keeps the audio and the next attempt
      // starts from the same sequence.
      return {
        kind: 'incomplete',
        reason: failure ?? 'transfer never completed',
        records,
        chunks: persisted.length
      }
    }

    // Persist BEFORE advancing. This ordering is the whole point: a pointer
    // moved ahead of durable storage tells the device to reuse space holding
    // audio that was never saved.
    try {
      for (const chunk of persisted) await sink.persist(chunk)
    } catch (error) {
      return {
        kind: 'incomplete',
        reason: `storing failed: ${error instanceof Error ? error.message : String(error)}`,
        records,
        chunks: persisted.length
      }
    }

    try {
      await transport.writeCommand(encodeRingAdvance(doneSeq))
    } catch (error) {
      // The audio is safely stored; failing to advance only means the next
      // drain re-reads it, which duplicates work but never loses anything.
      return {
        kind: 'incomplete',
        reason: `advance failed: ${error instanceof Error ? error.message : String(error)}`,
        records,
        chunks: persisted.length
      }
    }

    return { kind: 'drained', records, chunks: persisted.length, advancedTo: doneSeq }
  }

  /**
   * Waits for the transfer, enforcing both the first-data and overall bounds.
   * Returns null on success, or the reason it gave up.
   */
  private async waitFor(
    finished: Promise<void>,
    abort: AbortController,
    sawData: () => boolean
  ): Promise<string | null> {
    const { transport } = this.options
    let settled = false
    void finished.then(() => {
      settled = true
    })

    const firstData = await Promise.race([
      finished.then(() => 'finished' as const),
      transport.sleep(FIRST_DATA_TIMEOUT_MS, abort.signal).then(() => 'timeout' as const)
    ])
    if (firstData === 'finished') return null
    if (!sawData()) return 'device sent no data'

    const overall = await Promise.race([
      finished.then(() => 'finished' as const),
      transport.sleep(DRAIN_TIMEOUT_MS, abort.signal).then(() => 'timeout' as const)
    ])
    if (overall === 'finished' || settled) return null
    return 'transfer timed out'
  }
}
