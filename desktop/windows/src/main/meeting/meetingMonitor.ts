// The impure meeting-detection orchestrator: wires the native signal sources
// (ConsentStore watcher, foreground-change hook, process snapshot) into the
// pure detector state machine, and turns its effects into UX — the meeting
// toast and the capture-window auto-capture commands.
//
// Event-driven by design: evaluation runs only on (a) a ConsentStore registry
// change, (b) a foreground-window change, (c) a machine deadline (debounce /
// end-grace expiry), or (d) a settings change — never on a poll. Triggers are
// coalesced through a 250ms timer so a burst (app switch + mic grab) costs one
// snapshot.
import { app, type WebContents } from 'electron'
import { join } from 'path'
import { readFileSync } from 'fs'
import {
  step,
  initialDetectorState,
  type DetectorConfig,
  type DetectorEffect,
  type DetectorSignals,
  type DetectorState
} from './detector'
import {
  bundledPatterns,
  sanitizePatterns,
  matchTier1,
  pickAgreedMatch,
  type MeetingPatterns
} from './patterns'
import { listProcessNames } from './processSnapshot'
import { readMicCaptureEntries, watchMicConsentStore, type MicConsentWatcher } from './micConsentStore'
import { getForegroundExePath, getForegroundWindowTitle, subscribeForegroundChange } from '../usage/nativeForeground'
import { showMeetingToast, hideMeetingToast } from '../insight/toastWindow'
import { onCaptureEventInMain } from '../ipc/captureBridge'
import { getAppSettings, setAppSettings } from '../appSettings'
import type { CaptureCommand, MeetingToastAction } from '../../shared/types'

const DEBOUNCE_MS = 3000
const COALESCE_MS = 250

type Deps = { getCaptureWc: () => WebContents | null }

let deps: Deps | null = null
let patterns: MeetingPatterns | null = null
let state: DetectorState = initialDetectorState
let watcher: MicConsentWatcher | null = null
let unsubForeground: (() => void) | null = null
let unsubCaptureEvents: (() => void) | null = null
let coalesceTimer: NodeJS.Timeout | null = null
let deadlineTimer: NodeJS.Timeout | null = null
let running = false

// The meeting currently being surfaced/captured (set on 'meeting-started').
let currentMeeting: { id: string; appName: string; capturing: boolean } | null = null
let nextMeetingSeq = 1

// E2E only (OMI_E2E=1): when set, evaluate() uses these signals instead of the
// native sources, so the whole pipeline (machine → toast → capture command) is
// drivable hermetically from the _electron harness.
let injectedSignals: DetectorSignals | null = null
// E2E only: shrink debounce/grace + force mode so tests run in seconds.
let configOverride: Partial<DetectorConfig> | null = null
// E2E only: meeting-capture-status events seen by main (proves the full
// main → capture-window → main round trip without auth or network).
const statusLog: string[] = []

/** Load the pattern list: <userData>/meeting-patterns.json override when valid,
 *  else the bundled default. Read once per process (restart to pick up edits). */
function loadPatterns(): MeetingPatterns {
  if (patterns) return patterns
  try {
    const raw = readFileSync(join(app.getPath('userData'), 'meeting-patterns.json'), 'utf-8')
    const override = sanitizePatterns(JSON.parse(raw))
    if (override) {
      console.log('[meeting] using pattern override from userData/meeting-patterns.json')
      patterns = override
      return patterns
    }
    console.warn('[meeting] invalid meeting-patterns.json override — using bundled patterns')
  } catch {
    /* no override — the normal case */
  }
  patterns = bundledPatterns()
  return patterns
}

function config(): DetectorConfig {
  const m = getAppSettings().meeting
  return {
    debounceMs: DEBOUNCE_MS,
    endGraceMs: m.endGraceMinutes * 60_000,
    mode: m.mode,
    perApp: m.perApp,
    ...configOverride
  }
}

function computeSignals(): DetectorSignals {
  if (injectedSignals) return injectedSignals
  const p = loadPatterns()
  const tier2Ids = readMicCaptureEntries().map((e) => e.id)
  const matches = matchTier1(
    listProcessNames(),
    { exePath: getForegroundExePath(), title: getForegroundWindowTitle() },
    p
  )
  return {
    candidate: matches.length > 0,
    agreed: pickAgreedMatch(matches, tier2Ids, p),
    tier2Ids
  }
}

function sendCaptureCommand(cmd: CaptureCommand): void {
  const wc = deps?.getCaptureWc()
  if (!wc || wc.isDestroyed()) {
    console.warn('[meeting] no capture window — cannot send', cmd.type)
    return
  }
  // Main-originated command: tag with the capture window's own id (same pattern
  // as the E2E VAD hook) — meeting events are broadcast, not owner-routed.
  wc.send('omi-capture:cmd', { cmd, ownerId: wc.id })
}

function startCapture(): void {
  if (!currentMeeting || currentMeeting.capturing) return
  currentMeeting.capturing = true
  sendCaptureCommand({
    type: 'meeting-capture-start',
    meetingId: currentMeeting.id,
    appName: currentMeeting.appName
  })
}

function stopCapture(): void {
  if (!currentMeeting?.capturing) return
  currentMeeting.capturing = false
  sendCaptureCommand({ type: 'meeting-capture-stop', meetingId: currentMeeting.id })
}

/** Consume the one-time first-run flag (true exactly once). */
function takeFirstRun(): boolean {
  const s = getAppSettings().meeting
  if (s.firstRunToastShown) return false
  setAppSettings({ meeting: { ...s, firstRunToastShown: true } })
  return true
}

function handleEffect(effect: DetectorEffect): void {
  if (effect.type === 'meeting-started') {
    currentMeeting = {
      id: `meeting-${Date.now()}-${nextMeetingSeq++}`,
      appName: effect.match.name,
      capturing: false
    }
    console.log(
      `[meeting] started: ${effect.match.name} (${effect.match.tier2Key}) mode=${effect.mode}`
    )
    if (effect.mode === 'auto') startCapture()
    showMeetingToast({
      meetingId: currentMeeting.id,
      appName: currentMeeting.appName,
      kind: effect.mode === 'auto' ? 'capturing' : 'ask',
      firstRun: takeFirstRun()
    })
  } else {
    // meeting-ended: finalize the session (same stop path as the toast's Stop)
    // and drop the toast if it's still up.
    console.log(`[meeting] ended: ${effect.match.name}`)
    stopCapture()
    hideMeetingToast()
    currentMeeting = null
  }
}

/** True when detection can do nothing: global mode 'off' with no per-app
 *  override enabling anything. Skips the snapshot/registry work entirely while
 *  idle (injected E2E signals bypass the fast-path so tests stay in control). */
function detectionDisabled(): boolean {
  const m = getAppSettings().meeting
  return m.mode === 'off' && !Object.values(m.perApp).some((v) => v !== 'off')
}

function evaluate(): void {
  if (!running) return
  if (!injectedSignals && !configOverride && detectionDisabled() && state.phase === 'idle') return
  const now = Date.now()
  const result = step(state, computeSignals(), now, config())
  state = result.state
  for (const e of result.effects) handleEffect(e)
  if (deadlineTimer) {
    clearTimeout(deadlineTimer)
    deadlineTimer = null
  }
  if (result.deadline !== null) {
    deadlineTimer = setTimeout(evaluate, Math.max(50, result.deadline - now))
  }
}

/** Coalesce trigger bursts (foreground change + registry change) into one
 *  snapshot+evaluate pass. */
function scheduleEvaluate(): void {
  if (!running || coalesceTimer) return
  coalesceTimer = setTimeout(() => {
    coalesceTimer = null
    evaluate()
  }, COALESCE_MS)
}

/** A meeting-toast button was clicked (wired from ipc/meeting.ts). */
export function meetingToastAction(meetingId: string, action: MeetingToastAction): void {
  if (!currentMeeting || currentMeeting.id !== meetingId) {
    hideMeetingToast() // stale toast for a meeting that already ended
    return
  }
  if (action === 'start') {
    startCapture()
    showMeetingToast({ meetingId: currentMeeting.id, appName: currentMeeting.appName, kind: 'capturing' })
  } else if (action === 'stop') {
    stopCapture()
    hideMeetingToast()
  } else {
    hideMeetingToast()
  }
}

/** Settings changed (mode/grace/overrides) — re-evaluate against the new config. */
export function meetingSettingsChanged(): void {
  if (running) scheduleEvaluate()
}

export function startMeetingMonitor(d: Deps): void {
  if (running || process.platform !== 'win32') return
  deps = d
  running = true
  state = initialDetectorState
  // Tier 2 changes (the primary trigger): an app starting/stopping mic capture.
  watcher = watchMicConsentStore(scheduleEvaluate)
  if (!watcher) console.warn('[meeting] ConsentStore watcher unavailable — Tier 2 is event-blind')
  // Tier 1 title changes: switching to/away from a meeting tab.
  unsubForeground = subscribeForegroundChange(scheduleEvaluate)
  // Keep the toast honest: if the capture window reports an error, drop the
  // "Omi is capturing" notice instead of lying.
  unsubCaptureEvents = onCaptureEventInMain((ev) => {
    if (ev.type !== 'meeting-capture-status') return
    if (process.env.OMI_E2E === '1') statusLog.push(`${ev.meetingId}:${ev.status}`)
    if (!currentMeeting || ev.meetingId !== currentMeeting.id) return
    if (ev.status === 'error') {
      console.warn('[meeting] capture failed:', ev.message)
      currentMeeting.capturing = false
      hideMeetingToast()
    }
  })
  // Pick up a meeting already in progress at app start — coalesced, so the
  // first snapshot/registry read stays off the ready-to-show critical path.
  scheduleEvaluate()
  console.log('[meeting] monitor started')
}

export function stopMeetingMonitor(): void {
  if (!running) return
  running = false
  watcher?.stop()
  watcher = null
  unsubForeground?.()
  unsubForeground = null
  unsubCaptureEvents?.()
  unsubCaptureEvents = null
  if (coalesceTimer) clearTimeout(coalesceTimer)
  coalesceTimer = null
  if (deadlineTimer) clearTimeout(deadlineTimer)
  deadlineTimer = null
  stopCapture()
  currentMeeting = null
  state = initialDetectorState
  console.log('[meeting] monitor stopped')
}

/** E2E-only debug surface (guarded by OMI_E2E at the call site in index.ts):
 *  inject fake signals and read the machine phase, so the whole wiring is
 *  testable without Zoom or a real mic user. */
export function meetingDebug(): {
  inject: (sig: DetectorSignals | null) => void
  override: (cfg: Partial<DetectorConfig> | null) => void
  phase: () => string
  capturing: () => boolean
  statusLog: () => string[]
  running: () => boolean
} {
  return {
    // The monitor starts on ready-to-show — tests must wait for this before
    // injecting (an inject against a stopped monitor is dropped).
    running: () => running,
    inject: (sig): void => {
      injectedSignals = sig
      evaluate() // immediate, not coalesced — tests control timing explicitly
    },
    override: (cfg): void => {
      configOverride = cfg
    },
    phase: () => state.phase,
    capturing: () => !!currentMeeting?.capturing,
    statusLog: () => [...statusLog]
  }
}
