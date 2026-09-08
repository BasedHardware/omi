// Renderer-side voice test hook (Phase 6). Attaches window.__omiVoice ONLY in
// harness runs (OMI_E2E=1, surfaced via the preload `e2e` flag) so the smoke
// (scripts/run-voice-smoke.mjs) and the post-soak loop check
// (scripts/run-voice-loop-check.mjs) can drive the real controller without
// clicking through UI. Never attached in production.

import {
  getVoiceState,
  getVoiceEvents,
  startVoiceSession,
  stopVoiceSession,
  sendVoiceText,
  setVoiceOutputDevice,
  speakText
} from './voiceController'
import { beginRealtimeAudible, endRealtimeAudible, isRealtimeAudible } from './audibleOutputArbiter'
import { auth } from '../firebase'
import { liveConversation } from '../liveConversation'
import { setPreferences, type Preferences } from '../preferences'
import type { VoiceProvider } from './sessionMachine'

/** Harness-held realtime-audible token (never serialized across CDP). */
let e2eRealtimeAudibleToken: symbol | null = null

export function attachVoiceE2eHook(): void {
  if (window.omi?.e2e !== true) return
  ;(
    globalThis as unknown as {
      __omiVoice?: Record<string, unknown>
    }
  ).__omiVoice = {
    getState: getVoiceState,
    getEvents: getVoiceEvents,
    start: (provider?: VoiceProvider) => startVoiceSession(provider ?? 'openai'),
    stop: stopVoiceSession,
    say: sendVoiceText,
    speakTts: (text: string) => speakText(text),
    // Single-audible-owner arbiter probes (harness-only). Simulate a realtime lane
    // becoming/ending audible without a live provider, so a state-level test can
    // prove `speakTts` is denied while a realtime lane owns the speaker (the
    // "two voices at once" regression). The Symbol token is held here, never
    // crossing the CDP boundary.
    beginRealtimeAudible: () => {
      e2eRealtimeAudibleToken = beginRealtimeAudible()
    },
    endRealtimeAudible: () => {
      endRealtimeAudible(e2eRealtimeAudibleToken)
      e2eRealtimeAudibleToken = null
    },
    isRealtimeAudible: () => isRealtimeAudible(),
    setOutputDevice: (deviceId: string) => setVoiceOutputDevice(deviceId),
    listOutputs: async () => {
      const devices = await navigator.mediaDevices.enumerateDevices()
      return devices
        .filter((d) => d.kind === 'audiooutput')
        .map((d) => ({ deviceId: d.deviceId, label: d.label }))
    },
    // Loop-check support: the harness signs in by injecting a persisted Firebase
    // session, flips the continuousRecording pref, and reads the mirrored live
    // transcript to assert Omi's own words never appear as transcribed speech.
    getAuthUid: () => auth.currentUser?.uid ?? null,
    getLiveTranscript: () => ({
      status: liveConversation.getStatus(),
      segments: liveConversation.getSegments()
    }),
    setPrefs: (patch: Partial<Preferences>) => setPreferences(patch)
  }
}
