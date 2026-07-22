// Global-shortcut management, generalized so BOTH the overlay summon chord
// (overlay/shortcut.ts) and the mic record chord share one implementation.
//
// A "slot" owns a single accelerator: register/rebind-with-rollback/suspend/
// resume. globalShortcut is process-global, so keeping every claimed accelerator
// behind a slot (rather than scattered register() calls) is what lets rebinding
// release exactly the right chord and lets suspend/resume round-trip cleanly.
import { globalShortcut } from 'electron'
import { DEFAULT_RECORD_HOTKEY } from '../shared/hotkeyDefaults'

/** Default mic record chord. Rebindable + persisted (see appSettings). */
export { DEFAULT_RECORD_HOTKEY } from '../shared/hotkeyDefaults'

export interface ShortcutSlot {
  /** Attach the handler and claim an accelerator (the default, or `accelerator`
   *  when given). If the requested accelerator is taken it rolls back to the
   *  default so there's always a working binding. Returns whether it stuck. */
  register(onFire: () => void, accelerator?: string): boolean
  /** Attach the handler WITHOUT claiming anything from the OS. For a chord the
   *  user has turned off: the slot is live (getAccelerator/resume work, so a later
   *  enable re-claims it) but the accelerator is never registered — the whole point
   *  of Off is that another app keeps the chord. */
  setHandler(onFire: () => void): void
  /** Release the current (or a specific) accelerator. Idempotent. */
  unregister(accelerator?: string): void
  /** Rebind to a new accelerator, rolling back to the previous one if it is taken. */
  setAccelerator(accelerator: string): boolean
  /** Like setAccelerator but WITHOUT rollback: commit to `accelerator` as the
   *  current binding even if the OS can't claim it (registered=false). For the
   *  Record chord's intent model, where the user's exact choice is honored and a
   *  conflict is surfaced as a warning rather than silently reverted. */
  forceAccelerator(accelerator: string): boolean
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
    setHandler(onFire) {
      handler = onFire
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
    forceAccelerator(accelerator) {
      if (accelerator === currentAccelerator && globalShortcut.isRegistered(accelerator)) {
        return true
      }
      unregister(currentAccelerator)
      // Commit the requested chord as current regardless of OS acceptance; a
      // failed claim just means registered=false (the caller surfaces the conflict).
      currentAccelerator = accelerator
      return tryRegister(accelerator)
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

/** Create the record slot at `accelerator`, firing `onFire` on press.
 *  `claim: false` (the user turned the chord OFF) attaches the handler but never
 *  calls globalShortcut.register — so a disabled Ctrl+Space is never claimed, not
 *  even momentarily, at launch. A later enable resumes with the handler already
 *  attached. */
export function registerRecordShortcut(
  accelerator: string,
  onFire: () => void,
  opts?: { claim?: boolean }
): RecordShortcutState {
  recordSlot = createShortcutSlot(accelerator)
  if (opts?.claim === false) {
    recordSlot.setHandler(onFire)
    return { accelerator: recordSlot.getAccelerator(), registered: false }
  }
  const registered = recordSlot.register(onFire)
  return { accelerator: recordSlot.getAccelerator(), registered }
}

/** Rebind the record chord honoring the user's exact choice (no rollback). A
 *  conflict persists the requested chord with registered=false so the UI can warn,
 *  and a later relaunch re-attempts it once the conflicting app releases it. */
export function setRecordAcceleratorForced(accelerator: string): RecordShortcutState {
  if (!recordSlot) return { accelerator, registered: false }
  const registered = recordSlot.forceAccelerator(accelerator)
  return { accelerator: recordSlot.getAccelerator(), registered }
}

export function getRecordShortcut(): RecordShortcutState {
  if (!recordSlot) return { accelerator: DEFAULT_RECORD_HOTKEY, registered: false }
  return { accelerator: recordSlot.getAccelerator(), registered: recordSlot.isRegistered() }
}

/** Suspend the record chord while the settings UI captures raw keys — otherwise
 * pressing the CURRENT chord during a rebind fires the shortcut (navigates the
 * app away) instead of being captured. The overlay chord has its own
 * suspend/resume path (overlay/ipc.ts); the settings rebind suspends both. */
export function suspendRecordShortcut(): void {
  recordSlot?.suspend()
}

export function resumeRecordShortcut(): void {
  recordSlot?.resume()
}

/** Test-only: drop the record slot so suites start from a clean singleton. */
export function __resetRecordShortcutForTests(): void {
  recordSlot = null
}
