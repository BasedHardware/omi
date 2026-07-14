import { ipcMain, BrowserWindow } from 'electron'
import { readFile } from 'fs/promises'
import { resolve, sep } from 'path'
import { getPrimarySourceId } from '../rewind/sourceId'
import {
  listRewindFrames,
  searchRewindFrames,
  rewindDayBounds,
  getRewindFrameOcrLines,
  searchRewindEmbeddings,
  rewindFramesByIds
} from './db'
import { groupFrames } from '../rewind/rewindGrouping'
import { configureRewindEmbedSession, embedRewindQuery } from '../rewind/embeddingService'
import { mergeRewindSearchResults, type VectorHit } from '../rewind/vectorSearchMerge'
import {
  getRewindSettings,
  updateRewindSettings,
  ingestRewindFrame
} from '../rewind/captureService'
import { getCaptureDirective } from '../rewind/captureDirective'
import { pruneRewindOnce } from '../rewind/retentionRunner'
import { rewindRoot } from '../rewind/paths'
import type { RewindSettings } from '../../shared/types'

/** How many semantic neighbours to pull before the similarity floor + the
 *  already-in-FTS filter thin them out. */
const VECTOR_TOP_K = 50

/**
 * Semantic hits for a query, or [] when semantic search is unavailable (signed
 * out, embedding backend down, nothing indexed yet). Never throws: on macOS the
 * whole vector leg is a `try?`, and keyword results must render regardless.
 */
async function vectorHits(query: string): Promise<VectorHit[]> {
  try {
    const vec = await embedRewindQuery(query)
    if (!vec) return []
    const scored = await searchRewindEmbeddings(vec, VECTOR_TOP_K)
    const frames = rewindFramesByIds(scored.map((s) => s.frameId))
    const byId = new Map(frames.map((f) => [f.id, f]))
    return scored
      .map((s) => {
        const frame = byId.get(s.frameId)
        return frame ? { frame, similarity: s.similarity } : null
      })
      .filter((h): h is VectorHit => h !== null)
  } catch (e) {
    console.warn(`[rewind-embed] vector search failed, keyword-only: ${(e as Error).message}`)
    return []
  }
}

export function registerRewindHandlers(): void {
  ipcMain.handle('rewind:frames', async (_e, from: number, to: number) =>
    listRewindFrames(from, to)
  )
  ipcMain.handle('rewind:dayBounds', async () => rewindDayBounds())
  // Hybrid search: keyword (FTS5/BM25) then semantic (Gemini vectors), merged with
  // FTS leading and vectors adding recall only — see rewind/vectorSearchMerge.ts.
  // The two legs run in sequence, not in parallel: better-sqlite3 is synchronous,
  // so the FTS query occupies the thread outright and there is nothing for a
  // concurrent leg to interleave with. (A Promise.all here would have LOOKED
  // parallel while doing exactly this.) The vector leg is the slow one and it does
  // yield — see searchRewindEmbeddings.
  ipcMain.handle('rewind:search', async (_e, query: string) => {
    const q = query.trim()
    if (!q) return []
    const fts = searchRewindFrames(q)
    return groupFrames(mergeRewindSearchResults(fts, await vectorHits(q)), q)
  })
  // Relay of the renderer's Firebase session — the embedding indexer and the
  // query embedder are inert without it (the token only exists in the renderer).
  ipcMain.handle(
    'rewind:setEmbedSession',
    async (_e, s: { desktopApiBase: string; token: string } | null) =>
      configureRewindEmbedSession(s)
  )
  // --- Track 4 --- Per-line OCR bounding boxes for the search highlight overlay.
  ipcMain.handle('rewind:frameOcrLines', async (_e, frameId: number) =>
    getRewindFrameOcrLines(frameId)
  )
  ipcMain.handle('rewind:frameImage', async (_e, imagePath: string) => {
    const root = resolve(rewindRoot())
    const full = resolve(imagePath)
    if (full !== root && !full.startsWith(root + sep)) {
      throw new Error('invalid frame path')
    }
    const buf = await readFile(full)
    return `data:image/jpeg;base64,${buf.toString('base64')}`
  })
  ipcMain.handle('rewind:getSettings', async () => getRewindSettings())
  ipcMain.handle('rewind:setSettings', async (_e, next: RewindSettings) => {
    updateRewindSettings(next)
    const current = getRewindSettings()
    // Notify the renderer capture host so it can start/stop the stream and
    // re-pace immediately, without waiting for a re-mount or a poll.
    for (const w of BrowserWindow.getAllWindows()) {
      w.webContents.send('rewind:settings', current)
    }
    return current
  })
  // Current runtime capture directive (pause + effective cadence). The capture
  // host fetches this on mount, then reacts to pushes on 'rewind:capture-directive'.
  ipcMain.handle('rewind:getCaptureDirective', async () => getCaptureDirective())
  ipcMain.handle('rewind:pruneNow', async () => pruneRewindOnce())
  // Cached primary-screen id. The underlying desktopCapturer.getSources() can
  // take several seconds on some machines, so it's prewarmed at startup; this
  // is an instant cache hit in the normal case.
  ipcMain.handle('rewind:primarySourceId', async () => getPrimarySourceId())
  // Receive a sampled JPEG frame from the renderer capture host and store it
  // (after foreground-window metadata + idle/lock/dup gating).
  ipcMain.handle('rewind:saveFrame', async (_e, data: Uint8Array) =>
    ingestRewindFrame(Buffer.from(data))
  )
}
