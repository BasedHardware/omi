// Publish-scheduling policy for the bar↔main chat bridge (ChatBridgeHost). Kept
// in its own module so the decision is a pure, unit-testable function (no DOM,
// no timers) and so exporting it doesn't trip react-refresh in the component file.
//
// A streaming reply grows the last message on every SSE chunk; left unthrottled
// that fires a FULL-history publish (structured-cloned across the IPC boundary to
// the bar) ~20×/s, and the cost grows with thread length. So:
//   - status/flag transitions (stream start, stream end, TTS speaking) publish
//     PROMPTLY at the idle cadence — the bar reacts to state changes with no added
//     lag, and the terminal frame lands byte-identical the instant a stream ends;
//   - pure mid-stream history churn (same flags, text just growing) COALESCES to
//     the slower streaming cadence, halving the streaming publish rate.
// The bar always receives a full BarChatState snapshot (never a delta), so its
// render path is unchanged and the thread it settles on always matches Home's.
export const IDLE_PUBLISH_THROTTLE_MS = 50
export const STREAM_PUBLISH_THROTTLE_MS = 100

/**
 * Given the clock, when we last published, whether a reply is streaming, whether a
 * status/flag just changed, and whether a trailing publish is already pending,
 * decide whether to publish now, schedule a trailing publish, and/or pre-empt a
 * pending one.
 *
 * Invariant that keeps the bar byte-identical: a flag transition (which includes a
 * stream ENDING, sending true→false, carrying the completed message) always
 * publishes at the idle cadence and pre-empts any slower pending streaming timer,
 * so the final frame is never swallowed or delayed behind a coalesce window.
 */
export function planChatPublish(opts: {
  now: number
  lastPublishAt: number
  sending: boolean
  flagsChanged: boolean
  hasPendingTimer: boolean
}): { publishNow: boolean; scheduleInMs: number | null; clearPending: boolean } {
  const { now, lastPublishAt, sending, flagsChanged, hasPendingTimer } = opts
  const since = now - lastPublishAt
  if (flagsChanged) {
    // A transition (stream start/end, speaking start/stop): publish promptly at
    // the idle cadence, pre-empting any pending streaming-coalesce timer so the
    // fresh state (final frame on stream end) isn't held behind it.
    if (since >= IDLE_PUBLISH_THROTTLE_MS)
      return { publishNow: true, scheduleInMs: null, clearPending: true }
    return { publishNow: false, scheduleInMs: IDLE_PUBLISH_THROTTLE_MS - since, clearPending: true }
  }
  // Pure history churn: coalesce at the active cadence (harder while streaming).
  const throttle = sending ? STREAM_PUBLISH_THROTTLE_MS : IDLE_PUBLISH_THROTTLE_MS
  if (since >= throttle) return { publishNow: true, scheduleInMs: null, clearPending: false }
  if (!hasPendingTimer)
    return { publishNow: false, scheduleInMs: throttle - since, clearPending: false }
  return { publishNow: false, scheduleInMs: null, clearPending: false }
}
