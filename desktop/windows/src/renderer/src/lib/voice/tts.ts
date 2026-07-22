// Rust-backend TTS proxy client (Phase 6): POST /v1/tts/synthesize
// { text, voice_id } → audio/mpeg bytes (contract verified in
// Backend-Rust/src/routes/tts.rs — 4096-char cap, allowlisted OpenAI voices).
// Playback goes through the voice controller's gated output path so spoken
// non-realtime replies get the same echo protection as realtime audio.

import { desktopApi } from '../apiClient'

export const DEFAULT_TTS_VOICE = 'shimmer'
export const MAX_TTS_CHARS = 4096

export async function synthesizeTts(
  text: string,
  voiceId: string = DEFAULT_TTS_VOICE,
  // A barge-in / superseding reply aborts the in-flight chunk fetch so the
  // pending speakText resolves promptly (see voiceController.interruptCurrentResponse).
  signal?: AbortSignal
): Promise<Blob> {
  const trimmed = text.trim().slice(0, MAX_TTS_CHARS)
  if (!trimmed) throw new Error('tts: text is required')
  const res = await desktopApi.post<ArrayBuffer>(
    '/v1/tts/synthesize',
    { text: trimmed, voice_id: voiceId },
    { responseType: 'arraybuffer', timeout: 45_000, signal }
  )
  return new Blob([res.data], { type: 'audio/mpeg' })
}
