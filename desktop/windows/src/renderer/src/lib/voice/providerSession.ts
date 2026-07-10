// The seam between the voice controller and the two provider lanes (Phase 6).
// Both openaiSession and geminiSession implement this so the controller (state
// machine, echo gate, transcript injection, usage reporting) is provider-blind.

import type { RealtimeUsageBody } from './usageReport'

/** Shared spoken-assistant persona. The server locks the MODEL at token mint;
 *  everything else is client session config. */
export const OMI_VOICE_INSTRUCTIONS =
  'You are Omi, a personal AI companion speaking with the user on their Windows computer. ' +
  'Be warm, natural, and concise — this is a spoken conversation, so keep replies short ' +
  'and conversational. If the user interrupts you, stop and listen.'

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
