import { ipcMain, BrowserWindow } from 'electron'
import {
  getPrimarySourceId,
  getRewindCaptureSourceId,
  getRewindCaptureDiagnostics,
  isCurrentRewindCaptureSource
} from '../rewind/sourceId'
import {
  listRewindFrames,
  listRewindFramesSampled,
  searchRewindFrames,
  rewindDayBounds,
  rewindFrameCount,
  getRewindFrameOcrLines,
  searchRewindEmbeddings,
  rewindFramesByIds,
  getJitDatabase
} from './db'
import { isJitConversationKeyframePinned, type JitMirrorDb } from '../jit/jitTriggerMirror'
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
import { rebuildRewindIndexFromDisk } from '../rewind/rebuildIndex'
import { rewindRoot } from '../rewind/paths'
import { readRewindFrame } from '../rewind/frameFile'
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

// Monotonic id for the newest search. The vector leg is slow and its result is
// delivered out-of-band, so a stale one must never overwrite a newer query's
// results (type "invoice", then "receipt": invoice's vectors land last).
let searchSeq = 0

export function registerRewindHandlers(
  options: { focusFrame?: (frameId: number) => void } = {}
): void {
  ipcMain.handle('rewind:frames', async (_e, from: number, to: number) =>
    listRewindFrames(from, to)
  )
  // A day's frames, evenly down-sampled to ~500 (macOS parity + row-limit backstop).
  // The day-scoped timeline loads through this; 'rewind:frames' stays the unsampled
  // primitive for the small incremental live-append.
  ipcMain.handle('rewind:framesSampled', async (_e, from: number, to: number) =>
    listRewindFramesSampled(from, to)
  )
  ipcMain.handle('rewind:dayBounds', async () => rewindDayBounds())
  ipcMain.handle('rewind:frameCount', async () => rewindFrameCount())
  ipcMain.handle('rewind:frameById', async (_e, id: number) => {
    if (!Number.isInteger(id) || id < 0) return null
    return rewindFramesByIds([id])[0] ?? null
  })
  ipcMain.handle('rewind:focusFrame', async (_e, id: number) => {
    if (!Number.isInteger(id) || id < 0) return { ok: false, state: 'unavailable' as const }
    if (rewindFramesByIds([id]).length === 0) {
      const pinned = isJitConversationKeyframePinned(getJitDatabase() as unknown as JitMirrorDb, id)
      return { ok: false, state: pinned ? ('pruned' as const) : ('unavailable' as const) }
    }
    options.focusFrame?.(id)
    return { ok: true, state: 'available' as const }
  })
  // Hybrid search, in TWO PHASES.
  //
  // Phase 1 (this handler, synchronous): keyword results (FTS5/BM25), returned
  // immediately. Phase 2 (below, out-of-band): the same list with semantic hits
  // merged in, pushed on 'rewind:search-results' when — and if — they arrive.
  //
  // Keyword search must NEVER wait on the network, and it used to: the handler
  // awaited the query embedding, which is up to 3 attempts x a 30s timeout plus
  // backoff — about 91 seconds on a captive-portal/flaky network. The FTS rows
  // were sitting in hand from the first millisecond the whole time, and the user
  // stared at an empty result list. Vector search is ADDITIVE recall; its failure
  // is supposed to degrade silently to keyword-only (macOS wraps the whole leg in
  // `try?`), which is only true if keyword results don't depend on it.
  ipcMain.handle('rewind:search', async (e, query: string) => {
    const q = query.trim()
    if (!q) return []
    const seq = ++searchSeq
    const fts = searchRewindFrames(q)

    // Fire-and-forget: nothing about the reply below depends on this resolving,
    // and it must never reject into the handler.
    void (async () => {
      const hits = await vectorHits(q)
      if (hits.length === 0) return // keyword-only; the phase-1 reply already stands
      if (seq !== searchSeq) return // a newer query has since been issued
      if (e.sender.isDestroyed()) return
      // Which frames were keyword hits, so groupFrames can flag the purely-semantic
      // groups (those that exist only because vector recall added them).
      const keywordIds = new Set(fts.map((f) => f.id).filter((id): id is number => id != null))
      e.sender.send('rewind:search-results', {
        query: q,
        groups: groupFrames(mergeRewindSearchResults(fts, hits), q, { keywordIds })
      })
    })()

    return groupFrames(fts, q)
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
    const buf = await readRewindFrame(rewindRoot(), imagePath)
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
  // Recovery affordance: re-create rewind_frames rows for the JPEGs still on disk
  // after a whole-DB reset/recovery wiped them (surfaced from DbRecoveryNotice).
  // Only ever INSERTs missing rows — never deletes, idempotent. Returns the count.
  ipcMain.handle('rewind:rebuildIndex', async () => rebuildRewindIndexFromDisk())
  // Cached primary-screen id. The underlying desktopCapturer.getSources() can
  // take several seconds on some machines, so it's prewarmed at startup; this
  // is an instant cache hit in the normal case.
  ipcMain.handle('rewind:primarySourceId', async () => getPrimarySourceId())
  // Rewind follows the foreground window across displays while retaining one
  // persistent stream. Source enumeration is cached; each lookup is cheap.
  ipcMain.handle('rewind:captureSourceId', async () => getRewindCaptureSourceId())
  // UI-facing seam for a getSources() failure (see sourceId.ts): the Rewind tab
  // calls this once on mount to show a real error instead of capture just
  // never starting with only a console line.
  ipcMain.handle('rewind:captureDiagnostics', async () => getRewindCaptureDiagnostics())
  // Receive a sampled JPEG frame from the renderer capture host and store it
  // (after foreground-window metadata + idle/lock/dup gating).
  ipcMain.handle('rewind:saveFrame', async (_e, data: Uint8Array, sourceId: string) => {
    // Foreground focus can move again while getUserMedia opens a new display.
    // Never attach the new window's metadata/privacy decision to stale pixels.
    if (!(await isCurrentRewindCaptureSource(sourceId))) {
      return { captured: false, reason: 'display-changed' }
    }
    const result = await ingestRewindFrame(Buffer.from(data))
    // A stored frame bumps the all-time frame count. Tell open windows so the
    // Hub's "Screenshots" stat re-reads live instead of freezing at whatever it
    // was when the Hub mounted (it fetches the count once and has no other
    // refresh trigger). Only fire when a frame was actually stored — deduped /
    // idle / locked frames don't change the count.
    if (result.captured) {
      for (const w of BrowserWindow.getAllWindows()) {
        if (!w.isDestroyed()) w.webContents.send('rewind:captured')
      }
    }
    return result
  })
}
