// Overlay-compat IPC. The floating overlay window was replaced by the top-edge
// BAR (main/bar/window.ts) — its expanded state IS the old overlay chat — but
// the `overlay:*` channel names remain the renderer-facing API so onboarding
// (shortcut step, voice step, ask-demo step) keeps working untouched. This
// module routes those channels to the bar.
import { ipcMain, BrowserWindow } from 'electron'
import { hideBar, setBarEnabled, setSummonGestureAccelerator } from '../bar/window'
import {
  setOverlayAccelerator,
  suspendOverlayShortcut,
  resumeOverlayShortcut,
  getOverlayAccelerator
} from './shortcut'

/**
 * Wire the overlay-compat IPC channels. Renderer → main: hide, focusMain,
 * setEnabled, plus shortcut rebinding (setAccelerator) and suspend/resume used
 * while the onboarding step records a custom shortcut. Main → renderer
 * 'overlay:shown'/'overlay:summoned'/'overlay:visibility' are sent from
 * bar/window.ts.
 */
export function registerOverlayHandlers(focusMain: () => void): void {
  ipcMain.on('overlay:hide', () => hideBar())
  ipcMain.on('overlay:setEnabled', (_e, enabled: boolean) => setBarEnabled(!!enabled))
  ipcMain.on('overlay:focusMain', () => {
    hideBar()
    focusMain()
  })

  // Rebind the global summon accelerator. Returns whether the new accelerator
  // was claimed (false → it's taken; main rolled back to the previous binding).
  // On success the bar's gesture machine is rebuilt so tap/hold detection
  // samples the NEW chord's key.
  ipcMain.handle('overlay:setAccelerator', (_e, accelerator: string): boolean => {
    if (typeof accelerator !== 'string' || !accelerator.trim()) return false
    const ok = setOverlayAccelerator(accelerator)
    if (ok) setSummonGestureAccelerator(getOverlayAccelerator())
    return ok
  })
  // Release/re-claim the accelerator so the renderer can read raw keys while
  // recording a custom shortcut (otherwise the registered combo is swallowed).
  ipcMain.on('overlay:suspendShortcut', () => suspendOverlayShortcut())
  ipcMain.handle('overlay:resumeShortcut', (): boolean => resumeOverlayShortcut())

  // The bar reports a captured push-to-talk transcript; relay it to every
  // window so the onboarding voice step knows the user completed a voice ask.
  ipcMain.on('overlay:voiceCaptured', () => {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) w.webContents.send('overlay:voiceCaptured')
    }
  })

  // The bar reports any message sent (typed or spoken); relay it so the
  // onboarding demo step knows the user asked something in the bar.
  ipcMain.on('overlay:asked', () => {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) w.webContents.send('overlay:asked')
    }
  })
}
