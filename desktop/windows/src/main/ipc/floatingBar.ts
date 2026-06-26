import { BrowserWindow, ipcMain } from 'electron'
import { getFloatingBarSettings, setFloatingBarSettings } from '../floatingBar/settings'
import { applyFloatingBarSettings, getOverlayRuntimeStatus } from '../overlay/window'
import {
  getOverlayAccelerator,
  isOverlayShortcutRegistered,
  setOverlayAccelerator
} from '../overlay/shortcut'
import type { FloatingBarSettings, FloatingBarStatus } from '../../shared/types'

function broadcastFloatingBarSettings(settings: FloatingBarSettings): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('floatingBar:settings', settings)
  }
}

function floatingBarStatus(): FloatingBarStatus {
  const settings = getFloatingBarSettings()
  return {
    settings,
    ...getOverlayRuntimeStatus(settings),
    shortcutRegistered: isOverlayShortcutRegistered(),
    currentShortcut: getOverlayAccelerator()
  }
}

export function registerFloatingBarHandlers(): void {
  ipcMain.handle('floatingBar:getSettings', async () => getFloatingBarSettings())
  ipcMain.handle('floatingBar:setSettings', async (_e, next: FloatingBarSettings) => {
    const previous = getFloatingBarSettings()
    let saved = setFloatingBarSettings(next)

    if (saved.summonShortcut !== previous.summonShortcut) {
      const ok = setOverlayAccelerator(saved.summonShortcut)
      if (!ok) {
        saved = setFloatingBarSettings({ ...saved, summonShortcut: previous.summonShortcut })
      }
    }

    applyFloatingBarSettings(saved)
    broadcastFloatingBarSettings(saved)
    return saved
  })
  ipcMain.handle('floatingBar:status', async () => floatingBarStatus())
}
