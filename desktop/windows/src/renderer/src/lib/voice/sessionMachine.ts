// Pure realtime-voice session state machine (Phase 6). No I/O, no timers — a
// deterministic reducer the voice controller drives and the UI renders, so every
// transition is unit-testable in node. Mirrors the shared LiveStatus vocabulary
// (idle/connecting/live/error) used by the continuous-recording store.
//
// Provider notes baked into the states:
//  - 'connecting' covers both the token mint and the provider handshake.
//  - 'live' carries the provider actually connected (the mint may have fallen
//    back openai→gemini), so the UI labels the true lane.
//  - 'error' carries retryable so the UI can offer "Try again" only when the
//    failure isn't structural (e.g. signed out vs a transient 503).

export type VoiceProvider = 'openai' | 'gemini'

// Settings-level provider choice (macOS RealtimeOmniProvider.selectedProvider).
// 'auto' (the out-of-the-box default) defers to autoModelSelector's daily
// quality/speed pick; a concrete value pins that lane. DISTINCT from
// VoiceProvider — the resolved lane the machine actually connects with is never
// 'auto' (resolveEffectiveVoiceProvider collapses it to a concrete provider,
// mirroring Mac's selectedProvider vs. effectiveProvider split).
export type VoiceProviderSetting = 'auto' | VoiceProvider

export type VoiceSessionState =
  | { status: 'idle' }
  | { status: 'connecting'; provider: VoiceProvider }
  | { status: 'live'; provider: VoiceProvider; muted: boolean }
  | { status: 'error'; message: string; retryable: boolean }

export type VoiceSessionEvent =
  // User asked to start; provider is the PREFERRED lane (mint may fall back).
  | { type: 'start'; provider: VoiceProvider }
  // The mint fell back to the other provider mid-connect.
  | { type: 'provider-changed'; provider: VoiceProvider }
  // The provider session is up and audio is flowing.
  | { type: 'connected' }
  // Mic mute toggled (live only).
  | { type: 'set-muted'; muted: boolean }
  // User ended the session (or the app is shutting the surface down).
  | { type: 'stop' }
  // Anything failed: mint, handshake, or a fatal mid-session drop.
  | { type: 'fail'; message: string; retryable: boolean }

export const initialVoiceState: VoiceSessionState = { status: 'idle' }

/** Pure transition. Illegal events for the current state are ignored (return the
 *  same state), so a late async callback can never corrupt the machine. */
export function transition(state: VoiceSessionState, event: VoiceSessionEvent): VoiceSessionState {
  switch (event.type) {
    case 'start':
      // Only from rest states — a second start while connecting/live is a no-op
      // (the controller guards too, but the machine must not regress on races).
      if (state.status === 'idle' || state.status === 'error') {
        return { status: 'connecting', provider: event.provider }
      }
      return state
    case 'provider-changed':
      if (state.status === 'connecting') {
        return { status: 'connecting', provider: event.provider }
      }
      return state
    case 'connected':
      if (state.status === 'connecting') {
        return { status: 'live', provider: state.provider, muted: false }
      }
      return state
    case 'set-muted':
      if (state.status === 'live') return { ...state, muted: event.muted }
      return state
    case 'stop':
      // Stop always lands in idle (even from error — it's the "dismiss" path).
      return state.status === 'idle' ? state : { status: 'idle' }
    case 'fail':
      // A failure after the user already stopped must not resurrect the surface.
      if (state.status === 'idle') return state
      return { status: 'error', message: event.message, retryable: event.retryable }
  }
}
