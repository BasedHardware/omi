// src/main/ipc/insight.ts
import { ipcMain } from 'electron'
import { getInsightSettings, updateInsightSettings } from '../insight/state'
import {
  showInsightToast,
  pauseInsightDismiss,
  resumeInsightDismiss,
  dismissInsightToast,
  openProactivityToast,
  isInsightToastSender
} from '../insight/toastWindow'
import type { ToastDeliveryHooks } from '../insight/deliveryHooks'
import { fireNativeInsight } from '../insight/notification'
import type { InsightPayload, InsightSettings } from '../../shared/types'

// Show an insight using the user's chosen style: the in-app acrylic toast
// ('omi') or a native Windows notification ('native'). Exported so the proactive
// assistants' notification throttle (assistants/core/notify.ts) delivers through
// the same one place, rather than growing a second toast path.
export function deliverInsight(p: InsightPayload, hooks?: ToastDeliveryHooks): void {
  if (getInsightSettings().notificationStyle === 'native') {
    if (hooks) fireNativeInsight(p, hooks)
    else fireNativeInsight(p)
  } else if (hooks) showInsightToast(p, hooks)
  else showInsightToast(p)
}

export function registerInsightHandlers(): void {
  ipcMain.handle('insight:getSettings', async () => getInsightSettings())
  ipcMain.handle('insight:setSettings', async (_e, patch: Partial<InsightSettings>) =>
    updateInsightSettings(patch)
  )
  ipcMain.on('insight:dismiss', (event) => {
    if (isInsightToastSender(event.sender.id)) dismissInsightToast('dismissed')
  })
  ipcMain.on('insight:proactivity-open', (event, itemID: string) => {
    if (isInsightToastSender(event.sender.id)) openProactivityToast(itemID)
  })
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

// Public main-process seam for the v2 feed consumer; wire types come from the spine.
export { presentProactivityNotification } from '../proactivity/notificationAdapter'
