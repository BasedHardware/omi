// Overlay summon shortcut. Thin wrapper over a shared shortcut slot (see
// ../shortcuts) so the overlay chord and the mic record chord share one
// register/rebind/suspend/resume implementation. Public API is preserved for
// callers (overlay/ipc.ts, index.ts) and the existing tests.
import { createShortcutSlot } from '../shortcuts'

/** Default summon shortcut. User-rebindable during onboarding (and persisted). */
export const OVERLAY_ACCELERATOR = 'Shift+Space'

const slot = createShortcutSlot(OVERLAY_ACCELERATOR)

/**
 * Register the overlay summon shortcut. Returns false if the accelerator is
 * already taken by another app. The app keeps running either way.
 */
export function registerOverlayShortcut(accelerator: string, onToggle: () => void): boolean {
  return slot.register(onToggle, accelerator)
}

export function unregisterOverlayShortcut(accelerator?: string): void {
  slot.unregister(accelerator)
}

/**
 * Rebind the summon shortcut: release the current accelerator and claim the new
 * one. On failure the previous accelerator is restored so the user is never left
 * with no working shortcut. Returns whether the new accelerator was claimed.
 */
export function setOverlayAccelerator(accelerator: string): boolean {
  return slot.setAccelerator(accelerator)
}

/** Temporarily release the global shortcut so the renderer can read raw keys
 *  (used while recording a custom shortcut). Idempotent. */
export function suspendOverlayShortcut(): void {
  slot.suspend()
}

/** Re-claim the current accelerator after a suspend. */
export function resumeOverlayShortcut(): boolean {
  return slot.resume()
}

/** The accelerator currently claimed (exposed for tests/diagnostics). */
export function getOverlayAccelerator(): string {
  return slot.getAccelerator()
}
