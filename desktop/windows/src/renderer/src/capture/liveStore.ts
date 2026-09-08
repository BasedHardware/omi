import { liveConversation } from '../lib/liveConversation'
import type { LiveStatus } from '../lib/liveConversation'
import type { LiveStoreOp, TranscriptLine } from '../../../shared/types'

// The capture window owns the always-on mic session, so it's the source of truth
// for the live transcript. This wrapper mutates the local liveConversation store
// AND broadcasts each mutation as a LiveStoreOp, so UI windows (which run pure UI)
// can mirror it via liveConversation.applyRemoteOp. Only the capture window's
// liveMicSession writes through here; UI windows only ever read/apply-remote.

function emit(op: LiveStoreOp): void {
  window.omi?.captureEmit({ type: 'live', op })
}

export const captureLiveStore = {
  getSegments(): TranscriptLine[] {
    return liveConversation.getSegments()
  },
  reset(): void {
    liveConversation.reset()
    emit({ op: 'reset' })
  },
  setStatus(status: LiveStatus, error?: string): void {
    liveConversation.setStatus(status, error)
    emit({ op: 'status', status, error })
  },
  appendLine(line: TranscriptLine): void {
    liveConversation.appendLine(line)
    emit({ op: 'append', line })
  },
  /** Mark the current transcript saved and broadcast the segments so the UI
   *  window can turn them into a pending (optimistically-titled) conversation. */
  saved(segments: TranscriptLine[]): void {
    liveConversation.markSaved()
    emit({ op: 'saved', segments })
  }
}
