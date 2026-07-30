import { useEffect } from 'react'
import { liveConversation } from '../../lib/liveConversation'
import { createPendingConversation } from '../../lib/pendingConversations'
import { refreshCloudConversations } from '../../lib/pageCache'
import { buildLocalGraph } from '../../lib/kgSynthesis'
import { maybeTriggerTranscriptionQuotaPopup } from '../../lib/usageLimit'

// Mirrors the capture window's live-conversation store into THIS (main) window and
// runs the UI side effects that used to live in liveMicSession. The always-on mic
// session now runs in the capture window; it broadcasts each store mutation as a
// LiveStoreOp, which we replay via applyRemoteOp so the LiveConversation view
// shows the live transcript. On the `saved` op we additionally turn the finalized
// segments into an optimistically-titled pending conversation and refresh the
// cloud list — deliberately here (a UI window) rather than in the capture window.
// Mounted once in the app shell, where ContinuousRecordingHost used to be.

// Force a local-KG rebuild so conversation-derived memories reach the brain map,
// throttled to once per 30 min (the rebuild is two LLM calls). Delayed so the
// backend has extracted memories from the just-saved conversation first.
let lastKgRebuildAt = 0
function requestKgRebuild(): void {
  const now = Date.now()
  if (now - lastKgRebuildAt < 30 * 60 * 1000) return
  lastKgRebuildAt = now
  setTimeout(() => void buildLocalGraph(), 120000)
}

// Re-fetch /v1/conversations now and a few times after, so a just-finalized
// conversation appears (and its title/emoji fill in) without a manual refresh.
function pollForNewConversation(): void {
  refreshCloudConversations()
  for (const delay of [4000, 12000, 30000]) {
    setTimeout(() => refreshCloudConversations(), delay)
  }
}

export function LiveMirrorHost(): null {
  useEffect(() => {
    return window.omi?.onCaptureEvent?.((ev) => {
      if (ev.type !== 'live') return
      liveConversation.applyRemoteOp(ev.op)
      // A quota-exhausted terminal error from the capture window can't raise the
      // upgrade modal there (separate renderer); do it here where the popup lives.
      if (ev.op.op === 'status') {
        maybeTriggerTranscriptionQuotaPopup(ev.op.status, ev.op.error)
      }
      if (ev.op.op === 'saved') {
        createPendingConversation(ev.op.segments)
        pollForNewConversation()
        requestKgRebuild()
      }
    })
  }, [])
  return null
}
