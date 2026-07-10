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
import type { VoiceProvider } from './sessionMachine'

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
    setOutputDevice: (deviceId: string) => setVoiceOutputDevice(deviceId),
    listOutputs: async () => {
      const devices = await navigator.mediaDevices.enumerateDevices()
      return devices
        .filter((d) => d.kind === 'audiooutput')
        .map((d) => ({ deviceId: d.deviceId, label: d.label }))
    }
  }
}
