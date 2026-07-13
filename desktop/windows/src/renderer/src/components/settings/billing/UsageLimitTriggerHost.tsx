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
  // TODO(stream-1 chat integration — see docs/mac-parity-audit/PARALLEL-PLAN.md
  // §Stream 1): replace this spinner-flag inference with an explicit
  // quota-exceeded signal from the chat engine once fix/windows-wiring-criticals'
  // useChat changes merge.
  const { chat } = useAppState()
  const wasSending = useRef(chat.sending)

  useEffect(() => {
    const finishedReply = wasSending.current && !chat.sending
    wasSending.current = chat.sending
    if (finishedReply) void maybeTriggerChatQuotaPopup(fetchChatQuota)
  }, [chat.sending])

  return null
}
