// Global-shortcut management, generalized so BOTH the overlay summon chord
// (overlay/shortcut.ts) and the mic record chord share one implementation.
//
// A "slot" owns a single accelerator: register/rebind-with-rollback/suspend/
// resume. globalShortcut is process-global, so keeping every claimed accelerator
// behind a slot (rather than scattered register() calls) is what lets rebinding
// release exactly the right chord and lets suspend/resume round-trip cleanly.
import { globalShortcut } from 'electron'

/** Default mic record chord. Rebindable + persisted (see appSettings). */
export const DEFAULT_RECORD_HOTKEY = 'Ctrl+Space'

export interface ShortcutSlot {
  /** Attach the handler and claim an accelerator (the default, or `accelerator`
   *  when given). If the requested accelerator is taken it rolls back to the
   *  default so there's always a working binding. Returns whether it stuck. */
  register(onFire: () => void, accelerator?: string): boolean
  /** Release the current (or a specific) accelerator. Idempotent. */
  unregister(accelerator?: string): void
  /** Rebind to a new accelerator, rolling back to the previous one if it is taken. */
  setAccelerator(accelerator: string): boolean
  /** Temporarily release the accelerator (e.g. to record raw keys). Idempotent. */
  suspend(): void
  /** Re-claim the accelerator after a suspend. */
  resume(): boolean
  getAccelerator(): string
  isRegistered(): boolean
}

export function createShortcutSlot(defaultAccelerator: string): ShortcutSlot {
  let currentAccelerator = defaultAccelerator
  let handler: (() => void) | null = null

  const tryRegister = (accelerator: string = currentAccelerator): boolean => {
    if (!handler) return false
    try {
      // Only truly claimed when register() returned true AND the probe confirms
      // it — the OS can silently decline a chord another app owns.
      const ok = globalShortcut.register(accelerator, handler)
      if (!(ok && globalShortcut.isRegistered(accelerator))) {
        console.warn(`[shortcut] "${accelerator}" is unavailable (already in use?)`)
        return false
      }
      currentAccelerator = accelerator
      return true
    } catch (e) {
      console.warn(`[shortcut] failed to register "${accelerator}":`, e)
      return false
    }
  }

  const unregister = (accelerator: string = currentAccelerator): void => {
    try {
      globalShortcut.unregister(accelerator)
    } catch {
      // Unregistering an unregistered accelerator is a no-op.
    }
  }

  return {
    register(onFire, accelerator) {
      handler = onFire
      if (accelerator && accelerator !== currentAccelerator) {
        const previous = currentAccelerator
        if (tryRegister(accelerator)) return true
        // Requested chord is taken — fall back to the default so the user is
        // never left without a working shortcut.
        tryRegister(previous)
        return false
      }
      return tryRegister(currentAccelerator)
    },
    unregister,
    setAccelerator(accelerator) {
      const previous = currentAccelerator
      if (accelerator === previous && globalShortcut.isRegistered(previous)) return true
      unregister(previous)
      if (tryRegister(accelerator)) return true
      // Roll back so the user is never left without a working shortcut.
      tryRegister(previous)
      return false
    },
    suspend() {
      unregister(currentAccelerator)
    },
    resume() {
      return globalShortcut.isRegistered(currentAccelerator)
        ? true
        : tryRegister(currentAccelerator)
    },
    getAccelerator() {
      return currentAccelerator
    },
    isRegistered() {
      return globalShortcut.isRegistered(currentAccelerator)
    }
  }
}

// --- Record chord ----------------------------------------------------------
// A single process-wide slot for the mic record hotkey. Created on first
// registration with the persisted accelerator so a rebind releases the right one.

let recordSlot: ShortcutSlot | null = null

export interface RecordShortcutState {
  accelerator: string
  /** false when the OS reports the chord already owned by another app. */
  registered: boolean
}

/** Claim the record chord at `accelerator`, firing `onFire` on press. */
export function registerRecordShortcut(
  accelerator: string,
  onFire: () => void
): RecordShortcutState {
  recordSlot = createShortcutSlot(accelerator)
  const registered = recordSlot.register(onFire)
  return { accelerator: recordSlot.getAccelerator(), registered }
}

/** Rebind the record chord. Rolls back to the previous binding if the new one is taken. */
export function setRecordAccelerator(accelerator: string): RecordShortcutState {
  if (!recordSlot) return { accelerator, registered: false }
  const ok = recordSlot.setAccelerator(accelerator)
  return { accelerator: recordSlot.getAccelerator(), registered: ok }
}

export function getRecordShortcut(): RecordShortcutState {
  if (!recordSlot) return { accelerator: DEFAULT_RECORD_HOTKEY, registered: false }
  return { accelerator: recordSlot.getAccelerator(), registered: recordSlot.isRegistered() }
}

/** Test-only: drop the record slot so suites start from a clean singleton. */
export function __resetRecordShortcutForTests(): void {
  recordSlot = null
}
