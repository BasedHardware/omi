/**
 * Drains devices that keep stored audio as a list of files (the LittleFS
 * firmware generation).
 *
 * Same safety ordering as the ring drain: a file is only deleted after its
 * audio is durably stored. The extra hazard here is indexing. The firmware
 * addresses files by their position in the listing and re-indexes what remains
 * downward after each delete, so deleting the lowest index first would silently
 * shift every later target onto the wrong file.
 *
 * Ported from Flutter `storage_sync.dart`.
 */

import {
  deletionOrder,
  encodeDeleteFile,
  encodeListFiles,
  encodeReadFile,
  encodeStorageStop,
  isTerminalStatus,
  parseFileList,
  parseStatusByte,
  unpackPayload,
  type StoredFile
} from './storageProtocol'
import { StorageChunker, stampFrames, type DrainedChunk } from './storageChunker'
import type { DrainSink, StorageTransport } from './ringDrain'

export const LIST_TIMEOUT_MS = 10_000
export const FILE_FIRST_DATA_TIMEOUT_MS = 5_000
export const FILE_TIMEOUT_MS = 10 * 60_000
/** The firmware waits this long after a stop before it will answer a listing. */
export const STOP_SETTLE_MS = 500

export interface FileDrainOptions {
  transport: StorageTransport
  sink: DrainSink
  framesPerSecond: number
  onProgress?: (progress: { file: number; ofFiles: number; chunks: number }) => void
}

export type FileDrainResult =
  | { kind: 'idle'; reason: 'nothing-to-read' | 'unsupported' }
  | { kind: 'drained'; files: number; chunks: number; deleted: number }
  | { kind: 'incomplete'; reason: string; files: number; chunks: number; deleted: number }

export class FileDrain {
  constructor(private readonly options: FileDrainOptions) {}

  /** Lists what the device is holding; null when it does not speak this protocol. */
  async listFiles(): Promise<StoredFile[] | null> {
    const { transport } = this.options
    // Any transfer left in flight by an interrupted session would interleave
    // its notifications with the listing.
    await transport.writeCommand(encodeStorageStop()).catch(() => undefined)
    await transport.sleep(STOP_SETTLE_MS, new AbortController().signal)

    return new Promise<StoredFile[] | null>((resolve) => {
      const abort = new AbortController()
      let settled = false
      const finish = (value: StoredFile[] | null): void => {
        if (settled) return
        settled = true
        abort.abort()
        unsubscribe()
        resolve(value)
      }
      const unsubscribe = transport.subscribe((bytes) => {
        const files = parseFileList(bytes)
        if (files !== null) finish(files)
      })
      void transport
        .writeCommand(encodeListFiles())
        .catch(() => finish(null))
        .then(() => transport.sleep(LIST_TIMEOUT_MS, abort.signal))
        .then((outcome) => {
          if (outcome === 'elapsed') finish(null)
        })
    })
  }

  async drain(): Promise<FileDrainResult> {
    const files = await this.listFiles()
    if (files === null) return { kind: 'idle', reason: 'unsupported' }
    const withAudio = files.filter((file) => file.sizeBytes > 0)
    if (withAudio.length === 0) return { kind: 'idle', reason: 'nothing-to-read' }

    let chunks = 0
    const stored: number[] = []
    for (const file of withAudio) {
      const read = await this.readFile(file)
      this.options.onProgress?.({
        file: stored.length + 1,
        ofFiles: withAudio.length,
        chunks
      })
      if (read.error !== null) {
        // Stop at the first failure: later files are still on the device and a
        // partial pass must not delete anything it could not store.
        await this.deleteStored(stored)
        return {
          kind: 'incomplete',
          reason: read.error,
          files: stored.length,
          chunks,
          deleted: stored.length
        }
      }
      try {
        for (const chunk of read.chunks) await this.options.sink.persist(chunk)
      } catch (error) {
        await this.deleteStored(stored)
        return {
          kind: 'incomplete',
          reason: `storing failed: ${error instanceof Error ? error.message : String(error)}`,
          files: stored.length,
          chunks,
          deleted: stored.length
        }
      }
      chunks += read.chunks.length
      stored.push(file.index)
    }

    const deleted = await this.deleteStored(stored)
    return { kind: 'drained', files: stored.length, chunks, deleted }
  }

  /**
   * Deletes the files whose audio is stored, highest index first so the
   * firmware's downward re-indexing never moves a pending target.
   */
  private async deleteStored(indices: number[]): Promise<number> {
    let deleted = 0
    for (const index of deletionOrder(indices)) {
      try {
        await this.options.transport.writeCommand(encodeDeleteFile(index))
        deleted += 1
      } catch {
        // A file that will not delete is re-read next pass, which duplicates
        // work but never loses audio.
        break
      }
    }
    return deleted
  }

  private async readFile(
    file: StoredFile
  ): Promise<{ chunks: DrainedChunk[]; error: string | null }> {
    const { transport } = this.options
    const chunker = new StorageChunker({ framesPerSecond: this.options.framesPerSecond })
    const chunks: DrainedChunk[] = []
    let sawData = false
    let error: string | null = null

    const abort = new AbortController()
    let settle: () => void = () => undefined
    const finished = new Promise<void>((resolve) => {
      settle = resolve
    })

    const unsubscribe = transport.subscribe((bytes) => {
      if (bytes.length === 1) {
        const status = parseStatusByte(bytes[0])
        if (isTerminalStatus(status)) {
          // `complete` and `empty` are clean endings; anything else is not.
          if (status.kind !== 'complete' && status.kind !== 'empty') {
            error = `device reported ${status.kind}`
          }
          settle()
        }
        return
      }
      // `[timestamp u32 BE][packed audio]`
      if (bytes.length <= 4) return
      sawData = true
      const epochSeconds = ((bytes[0] << 24) | (bytes[1] << 16) | (bytes[2] << 8) | bytes[3]) >>> 0
      const { frames, timestamps } = unpackPayload(bytes.subarray(4))
      const stamped = stampFrames(
        frames,
        epochSeconds > 0 ? epochSeconds : file.epochSeconds,
        timestamps,
        this.options.framesPerSecond
      )
      for (const chunk of chunker.push(stamped)) chunks.push(chunk)
    })

    try {
      await transport.writeCommand(encodeReadFile(file.index, 0))
      const first = await Promise.race([
        finished.then(() => 'finished' as const),
        transport.sleep(FILE_FIRST_DATA_TIMEOUT_MS, abort.signal).then(() => 'timeout' as const)
      ])
      if (first !== 'finished') {
        if (!sawData) {
          error = 'device sent no data'
        } else {
          const overall = await Promise.race([
            finished.then(() => 'finished' as const),
            transport.sleep(FILE_TIMEOUT_MS, abort.signal).then(() => 'timeout' as const)
          ])
          if (overall !== 'finished') error = 'file transfer timed out'
        }
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      abort.abort()
      unsubscribe()
    }

    for (const chunk of chunker.flush()) chunks.push(chunk)
    return { chunks, error }
  }
}
