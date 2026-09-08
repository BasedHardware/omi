// Capture-window half of the echo gate (Phase 6, layer 2). The voice surface
// (main window) decides WHEN Omi is audibly speaking — including the release
// hangover after the playback buffer drains (lib/voice/echoGate.ts) — and sends
// the final boolean as an 'assistant-speaking' capture command. This module is
// the capture window's single enforcement point: every continuous transcription
// lane wraps its PCM feed with wrapFeed(), so while the gate holds, NO frame of
// Omi's own voice can enter a VAD pre-roll or reach /v4/listen.
//
// TTL RESILIENCE: the sender lives in a different window that can reload or
// crash while the gate is ON — with a plain boolean that would deafen
// continuous transcription FOREVER (no gate-off would ever arrive). So an ON
// state expires unless re-asserted: the controller re-sends 'assistant-speaking'
// active:true every GATE_REASSERT_MS while Omi speaks, and this side treats an
// assertion older than GATE_TTL_MS as released. Worst-case deafness after a
// dead sender is one TTL window; worst-case leak after a capture-window restart
// is one re-assert interval (the next periodic re-assert re-engages the gate).
//
// Deliberately NOT gated: push-to-talk (explicit user speech) and the realtime
// session's own mic (provider server-VAD owns barge-in; gating it would deafen
// Omi to interruptions).

/** How long an 'assistant-speaking: true' assertion stays valid. */
export const GATE_TTL_MS = 5000
/** How often the sender re-asserts while the gate is held (< GATE_TTL_MS). */
export const GATE_REASSERT_MS = 2000

let speaking = false
let assertedAt = 0

export const assistantGate = {
  setSpeaking(active: boolean, now: number = Date.now()): void {
    speaking = active
    assertedAt = now
  },
  isPaused(now: number = Date.now()): boolean {
    return speaking && now - assertedAt < GATE_TTL_MS
  }
}

/** Wrap a PCM feed so frames are dropped (BEFORE any VAD pre-roll buffering)
 *  while the assistant is speaking. */
export function wrapFeed<T>(feed: (chunk: T) => void): (chunk: T) => void {
  return (chunk: T): void => {
    if (assistantGate.isPaused()) return
    feed(chunk)
  }
}
