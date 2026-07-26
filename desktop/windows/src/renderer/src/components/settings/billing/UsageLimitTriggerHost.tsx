import { useEffect, useRef } from 'react'
import { useAppState } from '../../../state/appState'
import { maybeTriggerChatQuotaPopup } from '../../../lib/usageLimit'
import { fetchChatQuota } from '../../../lib/billing'

/**
 * Raises the usage-limit popup when a chat send finishes against an exhausted
 * quota. The ONE app-wide chat engine emits `quotaCheckSeq` only after an actual
 * hosted-chat request settles; local automation, coding agents, and resets do
 * not emit it. The probe is cheap, silent on error, and shows the popup at most
 * once per session (guards live in lib/usageLimit). Mounted once at the app
 * root, main window only.
 */
export function UsageLimitTriggerHost(): null {
  const { chat } = useAppState()
  const lastQuotaCheckSeq = useRef(chat.quotaCheckSeq)

  useEffect(() => {
    if (lastQuotaCheckSeq.current === chat.quotaCheckSeq) return
    lastQuotaCheckSeq.current = chat.quotaCheckSeq
    void maybeTriggerChatQuotaPopup(fetchChatQuota)
  }, [chat.quotaCheckSeq])

  return null
}
