import { useEffect, useRef } from 'react'
import { useAppState } from '../../../state/appState'
import { mainChatQuotaGate } from '../../../hooks/useChat'

/**
 * Refreshes the main-window chat quota snapshot after an actual hosted request
 * settles. Local automation, coding agents, pre-dispatch failures, and resets do
 * not advance `quotaCheckSeq`, so they cannot refresh or reset the canonical
 * pre-send gate. Mounted once at the app root, main window only.
 */
export function UsageLimitTriggerHost(): null {
  const { chat } = useAppState()
  const lastQuotaCheckSeq = useRef(chat.quotaCheckSeq)

  useEffect(() => {
    if (lastQuotaCheckSeq.current === chat.quotaCheckSeq) return
    lastQuotaCheckSeq.current = chat.quotaCheckSeq
    void mainChatQuotaGate.sync()
  }, [chat.quotaCheckSeq])

  return null
}
