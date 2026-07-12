// Pure decision logic for the peek retract watchdog + the main-driven
// interactivity toggle. Extracted from window.ts so the race-prone rules are
// unit-testable without Electron, a real cursor, or IPC:
//
//  1. RETRACT — when may a summoned peek pill auto-hide? Only when NOTHING is
//     holding it open: not the E2E screenshot hold, not a renderer activity
//     hold (PTT/streaming/spoken reply), not an in-flight summon GESTURE (the
//     key is physically held — Bug B: the pill used to retract ~600ms into a
//     silent hold because the renderer's busy-derived hold hadn't armed yet),
//     and not the cursor sitting inside the footprint. Outside all holds, the
//     grace timer runs and retract fires once it elapses. The grace is
//     state-dependent: a freshly summoned pill the cursor has NOT yet reached
//     lingers longer (lingerMs) so it doesn't vanish before the user's hand
//     arrives (live bug: a tap summon retracted at 600ms while the cursor was
//     still at the working position); once the cursor has visited and left, the
//     short graceMs applies.
//
//  2. INTERACTIVITY — should the window hit-test (vs stay click-through)? The
//     cursor being over the pill's hit rect is the single source of truth, read
//     from the OS in main every poll tick. This replaces the async renderer
//     mouseenter → IPC round-trip that let a normal move-and-click land before
//     interactivity flipped on, so the click passed through the pill (Bug A).
//
//  3. WATCH PLAN — which halves run for the current bar mode. Interactivity runs
//     in every visible non-expanded mode (peek AND ptt) so a ptt-summoned pill
//     that lingers after release is as clickable as a tap-summoned one (Bug A
//     live gap); the retract grace is peek-only — a ptt pill's lifetime is owned
//     by the gesture/keepAlive, never the cursor watchdog.

export type WatchdogInput = {
  /** E2E screenshot hold (setPeekWatchSuspended) — pins the bar open. */
  suspended: boolean
  /** Renderer-driven hold (bar:keepAlive) — a voice/chat exchange is in flight. */
  activityHold: boolean
  /** A summon gesture is active (the hotkey is physically held / gap window). */
  gestureActive: boolean
  /** The OS cursor is inside the peek footprint (keeps the pill open). */
  cursorInFootprint: boolean
  /** The cursor has entered the footprint at least once since this reveal. False
   *  for a fresh summon the hand hasn't reached → the longer lingerMs grace. */
  hasBeenHovered: boolean
  /** When the cursor first went outside every hold, or null while held. */
  outsideSince: number | null
  now: number
  /** Grace once the cursor has visited the pill and then left. */
  graceMs: number
  /** Longer grace for a freshly summoned, never-visited pill. */
  lingerMs: number
}

export type WatchdogResult = {
  /** New outsideSince to store (null while any hold applies). */
  outsideSince: number | null
  /** The grace elapsed with nothing holding the pill — retract it now. */
  retract: boolean
}

/** Decide the next watchdog state. Pure: same inputs → same result. */
export function evaluatePeekWatchdog(i: WatchdogInput): WatchdogResult {
  const held = i.suspended || i.activityHold || i.gestureActive || i.cursorInFootprint
  if (held) return { outsideSince: null, retract: false }
  const since = i.outsideSince ?? i.now
  const grace = i.hasBeenHovered ? i.graceMs : i.lingerMs
  return { outsideSince: since, retract: i.now - since >= grace }
}

/** Which halves of the bar watch tick run for a given mode (see header §3). */
export function barWatchPlan(mode: 'peek' | 'expanded' | 'ptt' | null): {
  trackInteractivity: boolean
  runRetract: boolean
} {
  const visibleCollapsed = mode === 'peek' || mode === 'ptt'
  return { trackInteractivity: visibleCollapsed, runRetract: mode === 'peek' }
}

/** Whether the summon gesture should treat the bar as already OPEN (a clean,
 *  interactive presentation) rather than something to (re)reveal. A window that
 *  is merely shown — mid-retract (`hiding`) or shown-but-unpresented (`mode`
 *  null, e.g. a hide the OS didn't fully take) — is NOT open: a tap must
 *  re-present it, restarting the peek watch + interactivity, instead of being
 *  swallowed or toggling it shut. This is the stuck-window inversion fix: the
 *  gesture keyed off raw window visibility, so a tap during a retract's slide-out
 *  saw "visible", skipped showBar (peek watch never restarted → dead clicks) and
 *  closed the bar on release ("goes back up extremely quickly"). */
export function barGestureSeesOpen(s: {
  visible: boolean
  mode: 'peek' | 'expanded' | 'ptt' | null
  hiding: boolean
}): boolean {
  return s.visible && s.mode !== null && !s.hiding
}

/** The next interactivity (hit-testing) state for the window, driven by the OS
 *  cursor. While the E2E holds the bar open we freeze the current state so a
 *  screenshot run doesn't flip hit-testing under a parked cursor. */
export function nextInteractivity(args: {
  cursorOverPill: boolean
  interactive: boolean
  suspended: boolean
}): boolean {
  if (args.suspended) return args.interactive
  return args.cursorOverPill
}
