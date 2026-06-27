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
  ipcMain.handle('screenSynth:recordRun', async (_e, run: ScreenSynthRun) =>
    recordRun(run.lastRunAt, run.lastCount)
  )
}
