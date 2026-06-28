// src/main/ipc/insight.ts
import { ipcMain } from 'electron'
import { getInsightSettings, updateInsightSettings } from '../insight/state'
import {
  showInsightToast,
  hideInsightToast,
  pauseInsightDismiss,
  resumeInsightDismiss
} from '../insight/toastWindow'
import { fireNativeInsight } from '../insight/notification'
import { insertInsight, recentInsights } from './db'
import type { InsightPayload, InsightSettings } from '../../shared/types'

// Show an insight using the user's chosen style: the in-app acrylic toast
// ('omi') or a native Windows notification ('native').
function deliverInsight(p: InsightPayload): void {
  if (getInsightSettings().notificationStyle === 'native') fireNativeInsight(p)
  else showInsightToast(p)
}

export function registerInsightHandlers(): void {
  ipcMain.handle('insight:getSettings', async () => getInsightSettings())
  ipcMain.handle('insight:setSettings', async (_e, patch: Partial<InsightSettings>) =>
    updateInsightSettings(patch)
  )
  ipcMain.handle('insight:add', async (_e, p: InsightPayload) => {
    insertInsight(p)
  })
  ipcMain.handle('insight:recent', async (_e, limit: number) => recentInsights(limit))
  ipcMain.on('insight:show', (_e, p: InsightPayload) => deliverInsight(p))
  ipcMain.on('insight:dismiss', () => hideInsightToast())
  ipcMain.on('insight:hoverStart', () => pauseInsightDismiss())
  ipcMain.on('insight:hoverEnd', () => resumeInsightDismiss())
  // Settings "test notification": show an example in the user's chosen style.
  ipcMain.on('insight:test', () =>
    deliverInsight({
      headline: 'Test notification',
      advice: 'If you can see this, Omi notifications are working.',
      reasoning: 'Triggered from Settings.',
      category: 'other',
      sourceApp: 'Omi',
      confidence: 1
    })
  )
}
