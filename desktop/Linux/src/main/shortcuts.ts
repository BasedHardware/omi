import { globalShortcut } from 'electron'
import { settings } from './settings'
import { createFloatingBar, getFloatingBar } from './windows'

// Equivalent of GlobalShortcutManager.swift, the Ask Omi hotkey toggles the
// floating bar's input state (FloatingControlBarManager.toggleAIInput()).

let registered: string | null = null

function triggerAskOmi(): void {
  const bar = createFloatingBar()
  if (!bar.isVisible()) bar.showInactive()
  bar.webContents.send('floating:toggle-ask')
  bar.focus()
}

export function registerHotkeys(): void {
  const accel = settings.get().hotkey
  if (registered === accel) return
  if (registered) {
    try {
      globalShortcut.unregister(registered)
    } catch {}
    registered = null
  }
  if (!accel) return
  try {
    const ok = globalShortcut.register(accel, triggerAskOmi)
    if (ok) registered = accel
    else console.error('shortcuts: failed to register', accel)
  } catch (e) {
    console.error('shortcuts: invalid accelerator', accel, e)
  }
}

export function watchHotkeySettings(): void {
  settings.on('changed', () => registerHotkeys())
}

export function unregisterAll(): void {
  globalShortcut.unregisterAll()
  registered = null
}

export function sendToggleAsk(): void {
  getFloatingBar()?.webContents.send('floating:toggle-ask')
}
