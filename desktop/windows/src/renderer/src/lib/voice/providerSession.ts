// The seam between the voice controller and the two provider lanes (Phase 6).
// Both openaiSession and geminiSession implement this so the controller (state
// machine, echo gate, transcript injection, usage reporting) is provider-blind.

import type { RealtimeUsageBody } from './usageReport'

// The per-session system instruction (persona, <about_user>, calendar context)
// is assembled by the controller — see lib/voice/systemInstruction.ts — and
// handed to whichever lane starts. The server locks the MODEL at token mint;
// everything else, instructions included, is client session config.

export type ProviderSessionCallbacks = {
  /** The provider session is up and audio is flowing both ways. */
  onConnected: () => void
  /** The session cannot continue (handshake failed or a fatal mid-session drop). */
  onFatal: (message: string, retryable: boolean) => void
  /** Omi's voice became audible (echo gate: activate). */
  onSpeakingStart: () => void
  /** Omi's voice finished/drained/was interrupted (echo gate: start release). */
  onSpeakingEnd: () => void
  /** One completed spoken utterance, from provider SOURCE text (id is stable). */
  onUtterance: (utteranceId: string, text: string) => void
  /** Provider-reported token usage for the ledger (per-turn or cumulative-final,
   *  provider-dependent — the controller posts each body as-is). */
  onUsage: (body: RealtimeUsageBody) => void
}

export type ProviderSessionHandle = {
  /** Tear everything down (idempotent): provider socket, mic, playback. */
  stop: () => void
  /** Mute/unmute the user's mic into the provider. */
  setMuted: (muted: boolean) => void
  /** Route Omi's voice to a different output device mid-conversation. */
  setOutputDevice: (deviceId: string) => Promise<void>
  /** Send a typed user turn into the live conversation (the model replies with
   *  voice). Also how the loop-check harness makes Omi speak deterministically. */
  sendUserText: (text: string) => void
}
