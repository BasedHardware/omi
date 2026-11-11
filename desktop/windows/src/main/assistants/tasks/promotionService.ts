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
import { getLastPromotedAt, promoteIfNeeded } from './create'

// Mac `TaskPromotionService` safety-net cadence (TPS.swift:43 — the code is 60s; the
// stale "5-minute" doc comment loses to the code).
const SAFETY_TIMER_MS = 60_000

// Backoff ladder for the safety net, in ms. The net exists to discover staged rows
// created OUT OF BAND (another device, a backend extraction) — every in-app path that
// stages a task already promotes inline (create.ts:324) or on the task-complete /
// task-delete events (taskSyncEngine.ts:807, :884), and none of those go through this
// timer. So the timer's only job is discovery latency for a case that is rare and
// idle-shaped, while a flat 60s made it the single loudest request source in the app:
// a POST /v1/staged-tasks/promote every minute for the life of the process, ~1,440 a
// day, essentially all returning `promoted:false`. Each one costs the backend two full
// collection scans (staged_tasks + candidates) to answer "nothing".
//
// A tick that promotes something resets to the floor, so a backlog still drains one
// per minute exactly as before. Only a tick that finds nothing (or errors — the flat
// timer had NO backoff for a failing backend either) steps down the ladder. Worst-case
// out-of-band discovery latency becomes 10 minutes, which is inside Mac's own
// documented 5-minute intent and well inside the hours-to-days shape of the case.
const SAFETY_BACKOFF_MS = [SAFETY_TIMER_MS, 120_000, 300_000, 600_000] as const
// Session-wait cadence for the startup promote — mirrors register.ts:53–54 (the
// renderer relays the session a few seconds after startup).
const SESSION_POLL_MS = 5_000
const SESSION_POLL_MAX_ATTEMPTS = 60 // ~5 min

let started = false
let safetyTimer: ReturnType<typeof setTimeout> | null = null
let sessionPollTimer: ReturnType<typeof setInterval> | null = null
// Index into SAFETY_BACKOFF_MS for the NEXT safety tick.
let safetyStep = 0

/** Arm the next safety tick at the current ladder delay. No-op once stopped: a tick
 *  re-arms from inside its own promise chain, so a stop that lands while a promote is
 *  in flight would otherwise resurrect the timer after `stopTaskPromotionService`
 *  cleared it. `clearInterval` used to make that impossible for free. */
function scheduleSafetyTick(): void {
  if (!started) return
  const delay = SAFETY_BACKOFF_MS[Math.min(safetyStep, SAFETY_BACKOFF_MS.length - 1)]
  safetyTimer = setTimeout(() => {
    void runSafetyTick()
  }, delay)
  safetyTimer.unref?.() // never hold the process open
}

/** One safety-net pass, then re-arm at the delay this pass earned. */
async function runSafetyTick(): Promise<void> {
  // Signed out costs nothing and proves nothing about the backlog, so it must not
  // walk the ladder down — otherwise a long signed-out stretch would leave a
  // just-signed-in user on the slowest cadence.
  if (!getBackendSession()) {
    safetyStep = 0
    scheduleSafetyTick()
    return
  }
  const before = getLastPromotedAt()
  try {
    await promoteIfNeeded({ bypassDebounce: true })
  } finally {
    // A promote landed → there may be more behind it, so return to the 60s floor and
    // drain at the original rate. Nothing promoted (or the POST failed) → step down.
    safetyStep = getLastPromotedAt() !== before ? 0 : safetyStep + 1
    scheduleSafetyTick()
  }
}

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

  // Trigger 2 — safety-net timer, floor 60s. `bypassDebounce` beats the 30s inline
  // debounce so a strand always drains one task per tick. Self-scheduling rather than
  // setInterval so each tick can pick its own next delay off SAFETY_BACKOFF_MS.
  scheduleSafetyTick()

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
    clearTimeout(safetyTimer)
    safetyTimer = null
  }
  stopSessionPoll()
  safetyStep = 0
  started = false
}

/** Reset module-level timer/started state so a suite can restart the service. */
export function __resetPromotionServiceForTests(): void {
  stopTaskPromotionService()
}
