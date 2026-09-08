import { ipcMain } from 'electron'
import { listAppUsage } from './db'
import { getUsageSettings, setUsageSettings } from '../usage/usageSettings'
import {
  flushForegroundMonitor,
  pruneUsageNow,
  startForegroundMonitor,
  stopForegroundMonitor
} from '../usage/foregroundMonitor'
import { seedUserAssistOnce } from '../usage/userAssistSeed'
import type { UsageSettings } from '../../shared/types'

export function registerUsageHandlers(): void {
  ipcMain.handle('usage:list', async () => listAppUsage())
  // Force an immediate flush of the in-memory tally, then return the fresh rows.
  ipcMain.handle('usage:flush', async () => {
    flushForegroundMonitor()
    return listAppUsage()
  })
  ipcMain.handle('usage:getSettings', async () => getUsageSettings())
  ipcMain.handle('usage:setSettings', async (_e, next: UsageSettings) => {
    const saved = setUsageSettings(next)
    if (saved.enabled) {
      // First time tracking is turned on, seed historical usage (once-guarded).
      seedUserAssistOnce()
      startForegroundMonitor()
      // Apply a changed retention window now (startForegroundMonitor no-ops when
      // already running, so it wouldn't re-prune on its own).
      pruneUsageNow()
    } else {
      stopForegroundMonitor()
    }
    return saved
  })
}
