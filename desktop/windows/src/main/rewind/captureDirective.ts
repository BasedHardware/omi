import { powerMonitor, BrowserWindow } from 'electron'
import type { RewindCaptureDirective } from '../../shared/types'

/**
 * Runtime capture directive, owned by the main process and pushed to the renderer
 * capture host, SEPARATE from the user's persisted Rewind settings. It encodes the
 * things the OS tells us that the renderer can't see: whether capture should be
 * paused (sleep/lock) and how fast to sample (base cadence, slowed 3× on battery).
 *
 * When the renderer unpauses it acquires a FRESH getUserMedia stream, so an unpause
 * naturally reinitializes the capture source — the Windows analog of macOS's "reinit
 * capture service" on wake/unlock.
 *
 * The pure functions below (reducer + directive derivation) are unit-tested without
 * a real powerMonitor; the impure controller at the bottom binds the events and
 * pushes the computed directive to all windows.
 */

/** macOS `batteryCaptureIntervalMultiplier = 3.0`: capture 3× slower on battery. */
export const BATTERY_CAPTURE_INTERVAL_MULTIPLIER = 3
/** macOS wake settle: after `didWake`, wait 1.5s before restarting capture. */
export const RESUME_SETTLE_MS = 1500
/** macOS debounces screen lock/unlock within ~1s to ignore momentary flicker. */
export const LOCK_DEBOUNCE_MS = 1000

export type CaptureDirectiveState = {
  /** System is asleep/suspended (willSleep → didWake). */
  suspended: boolean
  /** Screen is locked (screenIsLocked → screenIsUnlocked). */
  locked: boolean
  /** Running on battery power (slows cadence). */
  onBattery: boolean
  /** Base sample interval from the user's Rewind settings (ms). */
  baseIntervalMs: number
}

export type PowerTransition =
  | 'suspend'
  | 'resume'
  | 'lock-screen'
  | 'unlock-screen'
  | 'on-battery'
  | 'on-ac'

/** Apply a single OS power/lock transition to the directive state (pure). */
export function reduceCaptureState(
  s: CaptureDirectiveState,
  e: PowerTransition
): CaptureDirectiveState {
  switch (e) {
    case 'suspend':
      return { ...s, suspended: true }
    case 'resume':
      return { ...s, suspended: false }
    case 'lock-screen':
      return { ...s, locked: true }
    case 'unlock-screen':
      return { ...s, locked: false }
    case 'on-battery':
      return { ...s, onBattery: true }
    case 'on-ac':
      return { ...s, onBattery: false }
  }
}

/** Derive the directive the renderer acts on from the current state (pure). */
export function computeCaptureDirective(s: CaptureDirectiveState): RewindCaptureDirective {
  const paused = s.suspended || s.locked
  const intervalMs = s.baseIntervalMs * (s.onBattery ? BATTERY_CAPTURE_INTERVAL_MULTIPLIER : 1)
  return { paused, intervalMs }
}

/**
 * macOS asymmetry: waking from sleep waits 1.5s to settle before restarting
 * capture, but an unlock restarts immediately. Everything else pushes instantly.
 */
export function pushDelayForTransition(e: PowerTransition): number {
  return e === 'resume' ? RESUME_SETTLE_MS : 0
}

/**
 * Debounce repeated identical lock/unlock events within the window (matches Mac's
 * 1s lock debounce) — a lock followed by an unlock still both apply; only a second
 * lock (or second unlock) inside the window is ignored as OS chatter. Pure.
 */
export function shouldApplyLockTransition(
  lastEvent: PowerTransition | null,
  lastEventAtMs: number,
  e: PowerTransition,
  nowMs: number,
  debounceMs = LOCK_DEBOUNCE_MS
): boolean {
  if (e !== 'lock-screen' && e !== 'unlock-screen') return true
  if (e === lastEvent && nowMs - lastEventAtMs < debounceMs) return false
  return true
}

// --- Impure controller: binds powerMonitor + pushes the directive ---

let state: CaptureDirectiveState = {
  suspended: false,
  locked: false,
  onBattery: false,
  baseIntervalMs: 1000
}
let bound = false
let lastLockEvent: PowerTransition | null = null
let lastLockEventAtMs = 0
let pendingPush: ReturnType<typeof setTimeout> | null = null

function pushDirective(): void {
  const directive = computeCaptureDirective(state)
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('rewind:capture-directive', directive)
  }
}

/** Apply an OS transition to state and (re)push the directive, honoring the
 *  wake-settle delay and the lock debounce. Exported for wiring; the pure helpers
 *  above cover the logic under test. */
export function applyPowerTransition(e: PowerTransition, nowMs = Date.now()): void {
  if (!shouldApplyLockTransition(lastLockEvent, lastLockEventAtMs, e, nowMs)) return
  if (e === 'lock-screen' || e === 'unlock-screen') {
    lastLockEvent = e
    lastLockEventAtMs = nowMs
  }
  state = reduceCaptureState(state, e)
  if (pendingPush) {
    clearTimeout(pendingPush)
    pendingPush = null
  }
  const delay = pushDelayForTransition(e)
  if (delay > 0) {
    // Wake settle: hold the (unpaused) directive for 1.5s before restarting.
    pendingPush = setTimeout(() => {
      pendingPush = null
      pushDirective()
    }, delay)
  } else {
    pushDirective()
  }
}

/** The directive the renderer should currently act on (for an initial fetch). */
export function getCaptureDirective(): RewindCaptureDirective {
  return computeCaptureDirective(state)
}

/** Update the base sample cadence (from persisted settings) and re-push. */
export function setBaseCaptureInterval(baseIntervalMs: number): void {
  if (state.baseIntervalMs === baseIntervalMs) return
  state = { ...state, baseIntervalMs }
  pushDirective()
}

/**
 * Bind powerMonitor once: seed the initial battery state and subscribe to the
 * power/lock transitions that drive cadence and pause. Idempotent.
 */
export function startCaptureDirective(baseIntervalMs: number): void {
  state = { ...state, baseIntervalMs, onBattery: powerMonitor.isOnBatteryPower() }
  if (bound) {
    pushDirective()
    return
  }
  bound = true
  powerMonitor.on('on-battery', () => applyPowerTransition('on-battery'))
  powerMonitor.on('on-ac', () => applyPowerTransition('on-ac'))
  // Sleep/lock pause the capture stream; wake/unlock unpause it (wake after a
  // 1.5s settle, unlock immediately — see pushDelayForTransition). The renderer's
  // per-frame `locked` gate in captureService stays as belt-and-suspenders.
  powerMonitor.on('suspend', () => applyPowerTransition('suspend'))
  powerMonitor.on('resume', () => applyPowerTransition('resume'))
  powerMonitor.on('lock-screen', () => applyPowerTransition('lock-screen'))
  powerMonitor.on('unlock-screen', () => applyPowerTransition('unlock-screen'))
  pushDirective()
}
