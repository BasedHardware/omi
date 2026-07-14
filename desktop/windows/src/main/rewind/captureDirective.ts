import { powerMonitor, BrowserWindow } from 'electron'
import type { RewindCaptureDirective } from '../../shared/types'

/**
 * Runtime capture directive, owned by the main process and pushed to the renderer
 * capture host, SEPARATE from the user's persisted Rewind settings. It encodes the
 * things the OS tells us that the renderer can't see: whether capture should be
 * paused (sleep/lock — wired in a later sub-feature) and how fast to sample (base
 * cadence, slowed 3× on battery).
 *
 * The pure functions below (reducer + directive derivation) are unit-tested without
 * a real powerMonitor; the impure controller at the bottom binds the events and
 * pushes the computed directive to all windows.
 */

/** macOS `batteryCaptureIntervalMultiplier = 3.0`: capture 3× slower on battery. */
export const BATTERY_CAPTURE_INTERVAL_MULTIPLIER = 3

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

export type PowerTransition = 'on-battery' | 'on-ac'

/** Apply a single OS power transition to the directive state (pure). */
export function reduceCaptureState(
  s: CaptureDirectiveState,
  e: PowerTransition
): CaptureDirectiveState {
  switch (e) {
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

// --- Impure controller: binds powerMonitor + pushes the directive ---

let state: CaptureDirectiveState = {
  suspended: false,
  locked: false,
  onBattery: false,
  baseIntervalMs: 1000
}
let bound = false

function pushDirective(): void {
  const directive = computeCaptureDirective(state)
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('rewind:capture-directive', directive)
  }
}

/** Apply an OS transition to state and re-push the directive. Exported for wiring;
 *  the pure helpers above cover the logic under test. */
export function applyPowerTransition(e: PowerTransition): void {
  state = reduceCaptureState(state, e)
  pushDirective()
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
 * power transitions that drive cadence. Idempotent.
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
  pushDirective()
}
