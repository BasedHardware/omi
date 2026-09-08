// E2E-only hooks for the capture window, installed ONLY when the app runs
// under the harness (OMI_E2E=1 → window.omi.isE2E). Lets the meeting E2E spec
// run REAL YAMNet inference on fixture PCM without audio devices: the harness
// base64-encodes raw 16kHz s16le PCM and gets the classifier verdict back.
import { createYamnetClassifier } from '../lib/capture/yamnetClassifier'
import { _loopbackVerdictsForTest } from './AudioSessionHost'

export function installCaptureE2EHooks(): void {
  if (!window.omi?.isE2E) return
  ;(window as unknown as Record<string, unknown>).__omiCaptureE2E = {
    /** base64(raw s16le 16kHz PCM) → 'speech' | 'music' | 'unknown'. */
    classifyPcmBase64: async (b64: string): Promise<string> => {
      const bin = atob(b64)
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      const pcm = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2))
      const classifier = await createYamnetClassifier()
      return classifier.classify(pcm)
    },
    /** Live music-gate verdict per active loopback session (run-meeting-live). */
    loopbackVerdicts: (): Record<string, string> => _loopbackVerdictsForTest()
  }
}
