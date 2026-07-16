// The Windows `TaskPromotionService` — a faithful port of macOS
// `TaskPromotionService.start()` (TaskPromotionService.swift:21–50). It owns the
// two promotion triggers that live OUTSIDE the inline post-extraction promote in
// create.ts:
//
//   1. STARTUP promote (Mac start()'s immediate fire, TPS.swift:26): a task staged
//      while the app was down should promote within seconds of sign-in instead of
//      waiting for the first safety-timer tick. On Windows the Firebase session is
//      relayed by the renderer a few seconds AFTER app-ready, so — like the
//      embedding-index backfill in register.ts:63–86 — we fire immediately if a
//      session already exists, else poll briefly for one, run once, and stop.
//
//   2. 60s SAFETY-NET timer (TPS.swift:39–50): every 60s call
//      `promoteIfNeeded({ bypassDebounce: true })`, so any staged backlog drains one
//      task per tick regardless of the 30s inline debounce. This is what fixes the
//      batch-strand bug — extraction stages N tasks per frame, the inline promote
//      only lands task 1 (tasks 2..N are debounced), and the timer promotes the rest.
//
// NO drain-until-empty loop: Mac promotes at most ONE task per trigger on purpose
// (`maxIterations = 1`, TPS.swift:78) — bursting promotions posts back-to-back "new
// task" notifications users perceived as spam; the 60s timer + on-complete/on-delete
// events fill the list one item at a time. Copying that avoids recreating that bug
// when task notifications land on Windows.
//
// The service imports `promoteIfNeeded` from ./create, so the inline, timer, and
// event triggers all share create.ts's module-level debounce/lock state
// (`lastPromotedAt` / `promotionInFlight`) — exactly like Mac's shared actor.
// `promoteIfNeeded` self-guards (no-session early-return, re-entrancy lock, epoch
// guard across the await), so a tick that fires with no session or across a
// sign-out is already safe with no extra guards here.
import { getBackendSession } from '../core/session'
import { promoteIfNeeded } from './create'

// Mac `TaskPromotionService` safety-net cadence (TPS.swift:43 — the code is 60s; the
// stale "5-minute" doc comment loses to the code).
const SAFETY_TIMER_MS = 60_000
// Session-wait cadence for the startup promote — mirrors register.ts:53–54 (the
// renderer relays the session a few seconds after startup).
const SESSION_POLL_MS = 5_000
const SESSION_POLL_MAX_ATTEMPTS = 60 // ~5 min

let started = false
let safetyTimer: ReturnType<typeof setInterval> | null = null
let sessionPollTimer: ReturnType<typeof setInterval> | null = null

/**
 * Start the promotion safety net + the one-shot startup promote. Idempotent (a
 * second call while running is a no-op). Runs UNCONDITIONALLY (not gated on
 * `taskEnabled`) — matches Mac, where the plugin starts the service regardless of
 * extraction gating, so backlog staged before a user toggled extraction off still
 * promotes. Sign-out safety lives inside `promoteIfNeeded` (re-reads the session,
 * epoch-guards every write).
 */
export function startTaskPromotionService(): void {
  if (started) return
  started = true

  // Trigger 2 — 60s safety-net timer. `bypassDebounce` beats the 30s inline
  // debounce so a strand always drains one task per tick.
  safetyTimer = setInterval(() => {
    void promoteIfNeeded({ bypassDebounce: true })
  }, SAFETY_TIMER_MS)
  safetyTimer.unref?.() // never hold the process open

  // Trigger 1 — startup promote. Fire immediately if signed in (Mac start()); else
  // poll for a session, fire once when it appears, and stop (register.ts pattern).
  if (getBackendSession()) {
    void promoteIfNeeded() // default debounce = Mac's immediate start() fire
    return
  }
  let attempts = 0
  sessionPollTimer = setInterval(() => {
    attempts += 1
    if (getBackendSession()) {
      stopSessionPoll()
      void promoteIfNeeded()
    } else if (attempts >= SESSION_POLL_MAX_ATTEMPTS) {
      stopSessionPoll() // never signed in this launch — the next launch retries
    }
  }, SESSION_POLL_MS)
  sessionPollTimer.unref?.()
}

function stopSessionPoll(): void {
  if (sessionPollTimer) {
    clearInterval(sessionPollTimer)
    sessionPollTimer = null
  }
}

/** Mac `stop()` analog — tests + symmetry only. NOT wired to a quit hook (the timer
 *  is unref'd; there is nothing to clean up at quit). */
export function stopTaskPromotionService(): void {
  if (safetyTimer) {
    clearInterval(safetyTimer)
    safetyTimer = null
  }
  stopSessionPoll()
  started = false
}

/** Reset module-level timer/started state so a suite can restart the service. */
export function __resetPromotionServiceForTests(): void {
  stopTaskPromotionService()
}
