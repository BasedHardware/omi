import { ipcMain, BrowserWindow } from 'electron'
import { readFile } from 'fs/promises'
import { resolve, sep } from 'path'
import { getPrimarySourceId } from '../rewind/sourceId'
import {
  listRewindFrames,
  searchRewindFrames,
  rewindDayBounds,
  getRewindFrameOcrLines
} from './db'
import { groupFrames } from '../rewind/rewindGrouping'
import {
  getRewindSettings,
  updateRewindSettings,
  ingestRewindFrame
} from '../rewind/captureService'
import { getCaptureDirective } from '../rewind/captureDirective'
import { pruneRewindOnce } from '../rewind/retentionRunner'
import { rewindRoot } from '../rewind/paths'
import type { RewindSettings } from '../../shared/types'

export function registerRewindHandlers(): void {
  ipcMain.handle('rewind:frames', async (_e, from: number, to: number) => listRewindFrames(from, to))
  ipcMain.handle('rewind:dayBounds', async () => rewindDayBounds())
  ipcMain.handle('rewind:search', async (_e, query: string) => {
    const q = query.trim()
    if (!q) return []
    return groupFrames(searchRewindFrames(q), q)
  })
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
