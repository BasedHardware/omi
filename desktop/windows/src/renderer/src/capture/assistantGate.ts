// Capture-window half of the echo gate (Phase 6, layer 2). The voice surface
// (main window) decides WHEN Omi is audibly speaking — including the release
// hangover after the playback buffer drains (lib/voice/echoGate.ts) — and sends
// the final boolean as an 'assistant-speaking' capture command. This module is
// the capture window's single enforcement point: every continuous transcription
// lane wraps its PCM feed with wrapFeed(), so while the gate holds, NO frame of
// Omi's own voice can enter a VAD pre-roll or reach /v4/listen.
//
// Deliberately NOT gated: push-to-talk (explicit user speech) and the realtime
// session's own mic (provider server-VAD owns barge-in; gating it would deafen
// Omi to interruptions).

let speaking = false

export const assistantGate = {
  setSpeaking(active: boolean): void {
    speaking = active
  },
  isPaused(): boolean {
    return speaking
  }
}

/** Wrap a PCM feed so frames are dropped (BEFORE any VAD pre-roll buffering)
 *  while the assistant is speaking. */
export function wrapFeed<T>(feed: (chunk: T) => void): (chunk: T) => void {
  return (chunk: T): void => {
    if (speaking) return
    feed(chunk)
  }
}
