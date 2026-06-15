import { globalShortcut } from 'electron'

/** Default summon shortcut. User-rebindable during onboarding (and persisted). */
export const OVERLAY_ACCELERATOR = 'Shift+Space'

// The accelerator currently claimed (so suspend/resume and rebinding can release
// the right one). Updated by registerOverlayShortcut / setOverlayAccelerator.
let currentAccelerator = OVERLAY_ACCELERATOR
// The toggle callback, kept so we can re-register after a suspend or a rebind.
let toggleHandler: (() => void) | null = null

/**
 * Register the overlay summon shortcut. Returns false if the accelerator is
 * already taken by another app (Electron's register() returns false / the key
 * is reported unregistered). The app keeps running either way.
 */
export function registerOverlayShortcut(accelerator: string, onToggle: () => void): boolean {
  toggleHandler = onToggle
  return tryRegister(accelerator)
}

function tryRegister(accelerator: string): boolean {
  if (!toggleHandler) return false
  try {
    const ok = globalShortcut.register(accelerator, toggleHandler)
    if (!ok || !globalShortcut.isRegistered(accelerator)) {
      console.warn(`[overlay] shortcut "${accelerator}" is unavailable (already in use?)`)
      return false
    }
    currentAccelerator = accelerator
    return true
  } catch (e) {
    console.warn(`[overlay] failed to register shortcut "${accelerator}":`, e)
    return false
  }
}

export function unregisterOverlayShortcut(accelerator: string = currentAccelerator): void {
  try {
    globalShortcut.unregister(accelerator)
  } catch {
    // ignore — unregistering an unregistered accelerator is a no-op
  }
}

/**
 * Rebind the summon shortcut: release the current accelerator and claim the new
 * one. On failure the previous accelerator is restored so the user is never left
 * with no working shortcut. Returns whether the new accelerator was claimed.
 */
export function setOverlayAccelerator(accelerator: string): boolean {
  const previous = currentAccelerator
  if (accelerator === previous && globalShortcut.isRegistered(previous)) return true
  unregisterOverlayShortcut(previous)
  if (tryRegister(accelerator)) return true
  // Roll back to the previous binding so summoning still works.
  tryRegister(previous)
  return false
}

/** Temporarily release the global shortcut so the renderer can read raw keys
 *  (used while recording a custom shortcut). Idempotent. */
export function suspendOverlayShortcut(): void {
  unregisterOverlayShortcut(currentAccelerator)
}

/** Re-claim the current accelerator after a suspend. */
export function resumeOverlayShortcut(): boolean {
  if (globalShortcut.isRegistered(currentAccelerator)) return true
  return tryRegister(currentAccelerator)
}

/** The accelerator currently claimed (exposed for tests/diagnostics). */
export function getOverlayAccelerator(): string {
  return currentAccelerator
}
