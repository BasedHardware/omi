// src/main/ipc/screenSynth.ts
import { ipcMain } from 'electron'
import { listRewindFrames } from './db'
import {
  getScreenSynthState,
  updateScreenSynthState,
  advanceWatermark,
  recordRun
} from '../screenSynth/state'
import type { ScreenFrameLite, ScreenSynthState, ScreenSynthRun } from '../../shared/types'

export function registerScreenSynthHandlers(): void {
  // Frames since the watermark, stripped to the fields synthesis needs (no image bytes).
  ipcMain.handle('screenSynth:framesSince', async (): Promise<ScreenFrameLite[]> => {
    const { watermarkTs } = getScreenSynthState()
    // +1 so we never re-emit the exact watermark frame.
    const frames = listRewindFrames(watermarkTs + 1, Date.now())
    return frames.map((f) => ({
      ts: f.ts,
      app: f.app,
      windowTitle: f.windowTitle,
      processName: f.processName,
      ocrText: f.ocrText
    }))
  })
  ipcMain.handle('screenSynth:getState', async () => getScreenSynthState())
  ipcMain.handle('screenSynth:setState', async (_e, patch: Partial<ScreenSynthState>) =>
    updateScreenSynthState(patch)
  )
  ipcMain.handle('screenSynth:advanceWatermark', async (_e, ts: number) => {
    if (typeof ts === 'number' && ts > 0) advanceWatermark(ts)
  })
  ipcMain.handle('screenSynth:recordRun', async (_e, run: ScreenSynthRun) => {
    // Guard a missing/partial payload (matches the advanceWatermark handler) so a
    // bad call no-ops instead of rejecting the renderer's invoke. Reject a
    // non-finite or non-positive lastRunAt and coerce lastCount to a finite,
    // non-negative count so NaN/Infinity/negative run metadata is never persisted.
    if (run && Number.isFinite(run.lastRunAt) && run.lastRunAt > 0) {
      const lastCount = Number.isFinite(run.lastCount) && run.lastCount >= 0 ? run.lastCount : 0
      recordRun(run.lastRunAt, lastCount)
    }
  })
}
