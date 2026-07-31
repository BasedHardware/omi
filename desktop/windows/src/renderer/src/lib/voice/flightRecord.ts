// Renderer tap into the main-process voice flight recorder (2026-07-18).
// Fire-and-forget and throw-proof: with no bridge (jsdom tests, an old preload)
// it is a silent no-op, so instrumented code paths never grow a failure mode.
//
// Privacy contract (same as the recorder's): pass bounded labels and numbers
// only — NEVER transcript text, audio content, or PII. Lengths are fine.

export function recordVoiceFlight(type: string, data?: Record<string, unknown>): void {
  try {
    ;(
      window as unknown as {
        omi?: { voiceFlightRecord?: (type: string, data?: Record<string, unknown>) => void }
      }
    ).omi?.voiceFlightRecord?.(type, data)
  } catch {
    /* recorder must never break the plane it observes */
  }
}
