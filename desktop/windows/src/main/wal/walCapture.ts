/**
 * Keeps the audio the transcription socket did not take.
 *
 * The listen socket has three ways of not taking a chunk: there is no session,
 * the socket is connecting and the bounded pre-connect buffer overflows, or the
 * socket is closing or already closed. Each of those used to end at a silent
 * `return`, so a network drop mid-conversation lost that audio permanently.
 * This module observes those dispositions, keeps a ledger per capture source,
 * and writes the windows worth keeping to disk so they can be uploaded later.
 *
 * Everything the ledger judges is per capture source (mic, system) because the
 * two are separate recordings that upload as separate files.
 */

import { makeWalEntry, walFileName, type WalEntry } from '../../shared/wal'
import { WalFrameLedger, type FrameDisposition, type WalChunk } from './frameLedger'
import { upsertWal, type WalDb } from './walStore'

/** Bytes per millisecond of the capture format (16 kHz mono signed 16-bit). */
const BYTES_PER_MS = 32
/** The codec the pipeline produces; the same bytes the socket would carry. */
export const CAPTURE_CODEC = 'pcm16'
export const CAPTURE_SAMPLE_RATE = 16_000
export const CAPTURE_FRAME_SIZE = 160

export interface WalCaptureDeps {
  db: WalDb
  /** Persists one window's bytes; returns the bytes actually written. */
  writeFile: (fileName: string, bytes: Uint8Array) => Promise<number>
  now: () => number
  /** Retains every window, not only ones that lost audio. */
  storeEverything?: () => boolean
  onStored?: (entry: WalEntry) => void
}

interface SourceState {
  ledger: WalFrameLedger
  conversationId: string | null
}

export class WalCapture {
  private sources = new Map<string, SourceState>()

  constructor(private readonly deps: WalCaptureDeps) {}

  /**
   * Records what happened to one fed chunk. `source` is the capture source the
   * chunk came from, which becomes the recording's device name.
   */
  observe(args: {
    source: string
    byteLength: number
    disposition: FrameDisposition
    bytes: Uint8Array
    conversationId?: string | null
  }): void {
    const state = this.stateFor(args.source)
    if (args.conversationId !== undefined && args.conversationId !== null) {
      state.conversationId = args.conversationId
    }
    const durationMs = Math.max(1, Math.round(args.byteLength / BYTES_PER_MS))
    state.ledger.push({
      // Copy: the caller's buffer is reused for the next chunk.
      bytes: args.bytes.slice(),
      capturedAtMs: this.deps.now(),
      durationMs,
      disposition: args.disposition
    })
  }

  /**
   * Resolves chunks that were held for a connecting socket. The socket flushes
   * them on open, so they did reach the backend; a discarded buffer did not.
   */
  resolveBuffered(source: string, disposition: 'sent' | 'missed', count?: number): number {
    const state = this.sources.get(source)
    if (state === undefined) return 0
    return state.ledger.resolveBuffered(disposition, count)
  }

  /** Judges what is ready and stores the windows worth keeping. */
  async flush(source: string): Promise<WalEntry[]> {
    const state = this.sources.get(source)
    if (state === undefined) return []
    return this.store(source, state, state.ledger.chunk())
  }

  /** Session end: judges everything left regardless of the delay. */
  async drain(source: string): Promise<WalEntry[]> {
    const state = this.sources.get(source)
    if (state === undefined) return []
    const stored = await this.store(source, state, state.ledger.drain())
    this.sources.delete(source)
    return stored
  }

  async flushAll(): Promise<WalEntry[]> {
    const stored: WalEntry[] = []
    for (const source of Array.from(this.sources.keys())) {
      stored.push(...(await this.flush(source)))
    }
    return stored
  }

  async drainAll(): Promise<WalEntry[]> {
    const stored: WalEntry[] = []
    for (const source of Array.from(this.sources.keys())) {
      stored.push(...(await this.drain(source)))
    }
    return stored
  }

  /** Drops buffered audio without storing it (sign-out, wipe). */
  reset(): void {
    this.sources.clear()
  }

  private stateFor(source: string): SourceState {
    const existing = this.sources.get(source)
    if (existing !== undefined) return existing
    const state: SourceState = {
      ledger: new WalFrameLedger({
        now: this.deps.now,
        storeEverything: this.deps.storeEverything?.() ?? false
      }),
      conversationId: null
    }
    this.sources.set(source, state)
    return state
  }

  private async store(source: string, state: SourceState, chunks: WalChunk[]): Promise<WalEntry[]> {
    const stored: WalEntry[] = []
    for (const chunk of chunks) {
      const entry = makeWalEntry({
        timerStart: chunk.timerStart,
        codec: CAPTURE_CODEC,
        sampleRate: CAPTURE_SAMPLE_RATE,
        channel: 1,
        seconds: chunk.seconds,
        frameSize: CAPTURE_FRAME_SIZE,
        totalFrames: chunk.totalFrames,
        syncedFrameOffset: chunk.syncedFrameOffset,
        device: source,
        // A window the socket took in full needs no upload, but is still
        // recorded so the UI can show it was captured and accounted for.
        status: chunk.fullySynced ? 'synced' : 'miss',
        storage: 'disk',
        conversationId: state.conversationId
      })
      const fileName = walFileName(entry)
      const bytes = concatFrames(chunk)
      let written = 0
      try {
        written = await this.deps.writeFile(fileName, bytes)
      } catch (error) {
        // Losing the write loses the audio, but a throw here would also stop
        // the session that is still recording.
        console.error(`[wal] failed to store ${fileName}: ${String(error)}`)
        continue
      }
      const persisted: WalEntry = {
        ...entry,
        filePath: fileName,
        sizeBytes: written === 0 ? bytes.byteLength : written
      }
      upsertWal(this.deps.db, persisted)
      stored.push(persisted)
      this.deps.onStored?.(persisted)
    }
    return stored
  }
}

function concatFrames(chunk: WalChunk): Uint8Array {
  const out = new Uint8Array(chunk.byteLength)
  let offset = 0
  for (const frame of chunk.frames) {
    out.set(frame.bytes, offset)
    offset += frame.bytes.byteLength
  }
  return out
}
