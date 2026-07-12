// Pure decision logic for the peek retract watchdog + the main-driven
// interactivity toggle. Extracted from window.ts so the two race-prone rules
// are unit-testable without Electron, a real cursor, or IPC:
//
//  1. RETRACT — when may a summoned peek pill auto-hide? Only when NOTHING is
//     holding it open: not the E2E screenshot hold, not a renderer activity
//     hold (PTT/streaming/spoken reply), not an in-flight summon GESTURE (the
//     key is physically held — Bug B: the pill used to retract ~600ms into a
//     silent hold because the renderer's busy-derived hold hadn't armed yet),
//     and not the cursor sitting inside the footprint. Outside all holds, the
//     grace timer runs and retract fires once it elapses.
//
//  2. INTERACTIVITY — should the window hit-test (vs stay click-through)? The
//     cursor being over the pill's hit rect is the single source of truth, read
//     from the OS in main every poll tick. This replaces the async renderer
//     mouseenter → IPC round-trip that let a normal move-and-click land before
//     interactivity flipped on, so the click passed through the pill (Bug A).

export type WatchdogInput = {
  /** E2E screenshot hold (setPeekWatchSuspended) — pins the bar open. */
  suspended: boolean
  /** Renderer-driven hold (bar:keepAlive) — a voice/chat exchange is in flight. */
  activityHold: boolean
  /** A summon gesture is active (the hotkey is physically held / gap window). */
  gestureActive: boolean
  /** The OS cursor is inside the peek footprint (keeps the pill open). */
  cursorInFootprint: boolean
  /** When the cursor first went outside every hold, or null while held. */
  outsideSince: number | null
  now: number
  graceMs: number
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
  if (i.outsideSince === null) return { outsideSince: i.now, retract: false }
  if (i.now - i.outsideSince >= i.graceMs) return { outsideSince: i.outsideSince, retract: true }
  return { outsideSince: i.outsideSince, retract: false }
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
