// Renderer-side LiveNotes test hook (PR8). Attaches window.__omiLiveNotes ONLY in
// harness runs (OMI_E2E=1, surfaced via the preload `e2e` flag) so the E2E
// (scripts/run-livenotes-e2e.mjs) can drive a FIXTURE live-transcript through the
// real store + monitor without a mic or the capture window, and read back the
// generated notes. Never attached in production.

import { liveConversation } from '../liveConversation'
import { liveNotesMonitor } from './liveNotesMonitor'
import type { TranscriptLine } from '../../../../shared/types'

export function attachLiveNotesE2eHook(): void {
  if (window.omi?.e2e !== true) return
  ;(globalThis as unknown as { __omiLiveNotes?: Record<string, unknown> }).__omiLiveNotes = {
    /** Push one finalized transcript line into the SAME store the monitor reads. */
    pushSegment: (line: TranscriptLine) => liveConversation.applyRemoteOp({ op: 'append', line }),
    /** Clear the live transcript (start a fresh session). */
    reset: () => liveConversation.applyRemoteOp({ op: 'reset' }),
    getNotes: () => liveNotesMonitor.getNotes(),
    noteCount: () => liveNotesMonitor.getNotes().length,
    isGenerating: () => liveNotesMonitor.isGenerating(),
    addManualNote: (text: string) => liveNotesMonitor.addManualNote(text),
    /** Stub the LLM boundary so the harness never hits the real Gemini proxy.
     *  `fail:true` makes generation throw (exercises the graceful-degrade path). */
    stubAi: (opts: { fail?: boolean; text?: string }) =>
      liveNotesMonitor.setGeneratorForTest(async () => {
        if (opts.fail) throw new Error('stubbed generation failure')
        return opts.text ?? 'stubbed note'
      })
  }
}
