/**
 * Scheduling compaction, and wiring it to Electron.
 *
 * Everything decision-shaped lives elsewhere and is tested without Electron:
 * grouping in `compactionPlan.ts`, the write/verify/claim ordering in
 * `compactor.ts`, the encode channel in `chunkBroker.ts`. This file is the
 * assembly — where `app`, `BrowserWindow` and the database actually appear.
 */

import { BrowserWindow, app } from 'electron'
import { stat } from 'fs/promises'
import { claimFrameIntoChunk, compactableRewindFrames } from '../../ipc/db'
import { readRewindFrame } from '../frameFile'
import { rewindRoot } from '../paths'
import { getRewindSettings } from '../captureService'
import { ChunkEncodeBroker, pickEncodeTarget, type EncodeResponse } from './chunkBroker'
import { readChunkFile, removeChunkFile, writeChunkFile } from './chunkFiles'
import { compactOnce, type CompactionResult } from './compactor'
import { removeRewindFrame } from '../frameFile'

/**
 * How often a pass runs.
 *
 * Compaction is pure housekeeping and its input only grows by a frame a second
 * at most, so this is deliberately slow. It matters more that a pass never
 * competes with capture than that the backlog clears quickly.
 */
const COMPACTION_INTERVAL_MS = 30 * 60_000
/** Never on launch: the app has better things to do for the first few minutes. */
const COMPACTION_STARTUP_DELAY_MS = 5 * 60_000

let broker: ChunkEncodeBroker | null = null
let running = false
let timer: ReturnType<typeof setInterval> | null = null

/** The renderer answers here. Registered by `registerRewindIpc`. */
export function settleChunkEncode(response: EncodeResponse): void {
  broker?.settle(response)
}

function ensureBroker(): ChunkEncodeBroker | null {
  const target = pickEncodeTarget(BrowserWindow.getAllWindows().map((w) => w.webContents))
  if (!target) return null
  // Rebuilt per pass rather than held: the window that answered last time may
  // be gone, and a broker bound to dead web contents fails every request.
  broker = new ChunkEncodeBroker((request) => {
    target.send('rewind:encode-chunk', {
      requestId: request.requestId,
      width: request.width,
      height: request.height,
      // Structured clone moves the buffers; the renderer gets real bytes.
      frames: request.frames
    })
  })
  const abort = (): void => broker?.abortAll('the encoding window closed')
  target.once('destroyed', abort)
  return broker
}

/**
 * Run one compaction pass.
 *
 * Returns a zeroed result rather than throwing when there is no window to
 * encode in: that is an ordinary state (every window closed, app in the tray),
 * not a failure worth logging every half hour.
 */
export async function compactRewindOnce(): Promise<CompactionResult> {
  const empty: CompactionResult = {
    chunksWritten: 0,
    framesCompacted: 0,
    bytesReclaimed: 0,
    skipped: []
  }
  if (running) return empty
  const encodeBroker = ensureBroker()
  if (!encodeBroker) return empty

  running = true
  const root = rewindRoot()
  try {
    return await compactOnce({
      nowMs: () => Date.now(),
      listCompactable: (olderThanMs, limit) => compactableRewindFrames(olderThanMs, limit),
      readJpeg: (absolutePath) => readRewindFrame(root, absolutePath),
      encode: (input) => encodeBroker.encode(input),
      writeChunk: (relativePath, bytes) => writeChunkFile(root, relativePath, bytes),
      readChunk: (relativePath) => readChunkFile(root, relativePath),
      removeChunk: (relativePath) => removeChunkFile(root, relativePath),
      claimFrame: (id, relativePath, offset) => claimFrameIntoChunk(id, relativePath, offset),
      deleteJpeg: (absolutePath) => removeRewindFrame(root, absolutePath),
      log: (message) => console.log(`[rewind] ${message}`)
    })
  } finally {
    running = false
  }
}

/**
 * Whether compaction should run at all.
 *
 * Off when Rewind capture is off — there is nothing arriving to compact, and a
 * user who has turned capture off has not asked us to keep rewriting their
 * history in the background.
 */
function compactionEnabled(): boolean {
  return getRewindSettings().captureEnabled
}

export function startRewindCompaction(): void {
  if (timer) return
  const tick = (): void => {
    if (!compactionEnabled()) return
    void compactRewindOnce().catch((e) => console.warn('[rewind] compaction pass failed:', e))
  }
  setTimeout(tick, COMPACTION_STARTUP_DELAY_MS).unref?.()
  timer = setInterval(tick, COMPACTION_INTERVAL_MS)
  timer.unref?.()
  app.once('before-quit', () => {
    if (timer) clearInterval(timer)
    timer = null
    broker?.abortAll('the app is quitting')
  })
}

/** Bytes a set of frames currently occupies as JPEGs, for the status surface. */
export async function jpegBytesOnDisk(paths: string[]): Promise<number> {
  let total = 0
  for (const path of paths) {
    try {
      total += (await stat(path)).size
    } catch {
      // A frame whose file is already gone contributes nothing.
    }
  }
  return total
}
