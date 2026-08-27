import { useEffect, useRef } from 'react'
import { useAppState } from '../../../state/appState'
import { mainChatQuotaGate } from '../../../hooks/useChat'

/**
 * Refreshes the main-window chat quota snapshot after each completed reply so
 * the next pre-send gate check in useChat.send() reads a fresh verdict without
 * a network round trip. Mounted once at the app root, main window only.
 */
export function UsageLimitTriggerHost(): null {
  const { chat } = useAppState()
  const wasSending = useRef(chat.sending)

  useEffect(() => {
    const finishedReply = wasSending.current && !chat.sending
    wasSending.current = chat.sending
    if (finishedReply) void mainChatQuotaGate.sync()
  }, [chat.sending])

  return null
}
