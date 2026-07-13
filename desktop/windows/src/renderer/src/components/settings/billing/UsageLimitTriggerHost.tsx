import { useEffect, useRef } from 'react'
import { useAppState } from '../../../state/appState'
import { maybeTriggerChatQuotaPopup } from '../../../lib/usageLimit'
import { fetchChatQuota } from '../../../lib/billing'

/**
 * Raises the usage-limit popup when a chat send finishes against an exhausted
 * quota. It observes the ONE app-wide chat engine's `sending` flag (via
 * useAppState) rather than touching the chat send path itself — on the
 * busy→idle edge (a reply just completed) it probes the chat quota once. The
 * probe is cheap, silent on error, and shows the popup at most once per session
 * (guards live in lib/usageLimit). Mounted once at the app root, main window
 * only.
 */
export function UsageLimitTriggerHost(): null {
  const { chat } = useAppState()
  const wasSending = useRef(chat.sending)

  useEffect(() => {
    const finishedReply = wasSending.current && !chat.sending
    wasSending.current = chat.sending
    if (finishedReply) void maybeTriggerChatQuotaPopup(fetchChatQuota)
  }, [chat.sending])

  return null
}
