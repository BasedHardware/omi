import { ipcMain, BrowserWindow, dialog } from 'electron'
import { rm } from 'fs/promises'
import { join } from 'path'
import { pathToFileURL } from 'url'
import { getPrimarySourceId } from '../rewind/sourceId'
import {
  deleteAllRewindFrames,
  getRewindFrame,
  listRewindFrames,
  searchRewindFrames,
  rewindDayBounds,
  rewindStatusStats
} from './db'
import { groupFrames } from '../rewind/rewindGrouping'
import {
  getRewindSettings,
  updateRewindSettings,
  ingestRewindFrame
} from '../rewind/captureService'
import { readRewindFrameImage, readRewindFrameImageDataUrl } from '../rewind/frameImage'
import { pruneRewindOnce } from '../rewind/retentionRunner'
import { rewindRoot } from '../rewind/paths'
import type { RewindFrameImageResult, RewindSettings } from '../../shared/types'
import { clearCurrentScreen } from '../rewind/currentScreen'
import { rendererBaseUrl } from '../rendererServer'

function trustedRendererUrl(url: string | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    const devUrl = process.env.ELECTRON_RENDERER_URL
    if (devUrl && parsed.origin === new URL(devUrl).origin) return true

    const packagedUrl = rendererBaseUrl()
    if (packagedUrl && parsed.origin === new URL(packagedUrl).origin) return true

    // Exact pathname match: allows hash/query routing on the renderer file
    // while rejecting sibling files like index.html.evil.
    const fallbackRendererFile = pathToFileURL(join(__dirname, '../renderer/index.html'))
    return parsed.protocol === 'file:' && parsed.pathname === fallbackRendererFile.pathname
  } catch {
    return false
  }
}

export function registerRewindHandlers(): void {
  ipcMain.handle('rewind:frames', async (_e, from: number, to: number) =>
    listRewindFrames(from, to)
  )
  ipcMain.handle('rewind:dayBounds', async () => rewindDayBounds())
  ipcMain.handle('rewind:search', async (_e, query: string) => {
    const q = query.trim()
    if (!q) return []
    return groupFrames(searchRewindFrames(q), q)
  })
  ipcMain.handle('rewind:frameImage', async (_e, imagePath: string) => {
    const dataUrl = await readRewindFrameImageDataUrl(imagePath, rewindRoot())
    if (!dataUrl) throw new Error('Frame image not found')
    return dataUrl
  })
  ipcMain.handle('rewind:frameById', async (_e, id: number): Promise<RewindFrameImageResult> => {
    const frame = Number.isSafeInteger(id) && id > 0 ? getRewindFrame(id) : null
    return readRewindFrameImage(frame, rewindRoot())
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
  ipcMain.handle('rewind:status', async () => rewindStatusStats())
  ipcMain.handle('rewind:pruneNow', async () => pruneRewindOnce())
  ipcMain.handle('rewind:deleteAll', async (event) => {
    if (!trustedRendererUrl(event.senderFrame?.url) && !trustedRendererUrl(event.sender.getURL())) {
      return { deleted: 0, canceled: true }
    }
    const parent = BrowserWindow.fromWebContents(event.sender)
    const choice = parent
      ? await dialog.showMessageBox(parent, {
          type: 'warning',
          buttons: ['Delete Rewind history', 'Cancel'],
          defaultId: 1,
          cancelId: 1,
          title: 'Delete Rewind history?',
          message: 'Delete all Rewind screenshots and screen text stored on this PC?',
          detail: 'This cannot be undone.'
        })
      : await dialog.showMessageBox({
          type: 'warning',
          buttons: ['Delete Rewind history', 'Cancel'],
          defaultId: 1,
          cancelId: 1,
          title: 'Delete Rewind history?',
          message: 'Delete all Rewind screenshots and screen text stored on this PC?',
          detail: 'This cannot be undone.'
        })
    if (choice.response !== 0) return { deleted: 0, canceled: true }
    const deleted = deleteAllRewindFrames()
    await rm(rewindRoot(), { recursive: true, force: true })
    clearCurrentScreen()
    for (const w of BrowserWindow.getAllWindows()) {
      w.webContents.send('rewind:cleared')
    }
    return { deleted }
  })
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
