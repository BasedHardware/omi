import { ipcMain, BrowserWindow } from 'electron'
import { hideOverlay, setOverlayHeight, setOverlayEnabled } from './window'
import {
  setOverlayAccelerator,
  suspendOverlayShortcut,
  resumeOverlayShortcut
} from './shortcut'

/**
 * Wire the overlay IPC channels. Renderer → main: hide, setHeight, focusMain,
 * setEnabled, plus shortcut rebinding (setAccelerator) and suspend/resume used
 * while the onboarding step records a custom shortcut. Main → renderer
 * 'overlay:shown'/'overlay:summoned' are sent directly from window.ts.
 */
export function registerOverlayHandlers(focusMain: () => void): void {
  ipcMain.on('overlay:hide', () => hideOverlay())
  ipcMain.on('overlay:setEnabled', (_e, enabled: boolean) => setOverlayEnabled(!!enabled))
  ipcMain.on('overlay:setHeight', (_e, px: number) => {
    if (typeof px === 'number' && px > 0) setOverlayHeight(px)
  })
  ipcMain.on('overlay:focusMain', () => {
    hideOverlay()
    focusMain()
  })

  // Rebind the global summon accelerator. Returns whether the new accelerator
  // was claimed (false → it's taken; main rolled back to the previous binding).
  ipcMain.handle('overlay:setAccelerator', (_e, accelerator: string): boolean => {
    if (typeof accelerator !== 'string' || !accelerator.trim()) return false
    return setOverlayAccelerator(accelerator)
  })
  // Release/re-claim the accelerator so the renderer can read raw keys while
  // recording a custom shortcut (otherwise the registered combo is swallowed).
  ipcMain.on('overlay:suspendShortcut', () => suspendOverlayShortcut())
  ipcMain.handle('overlay:resumeShortcut', (): boolean => resumeOverlayShortcut())

  // The overlay reports a captured push-to-talk transcript; relay it to every
  // window so the onboarding voice step knows the user completed a voice ask.
  ipcMain.on('overlay:voiceCaptured', () => {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) w.webContents.send('overlay:voiceCaptured')
    }
  })

  // The overlay reports any message sent (typed or spoken); relay it so the
  // onboarding demo step knows the user asked something in the bar.
  ipcMain.on('overlay:asked', () => {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) w.webContents.send('overlay:asked')
    }
  })
}
