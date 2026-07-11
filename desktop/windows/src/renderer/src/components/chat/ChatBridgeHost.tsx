import { useCallback, useEffect, useRef } from 'react'
import { useAppState } from '../../state/appState'
import type { BarChatState, BarChatStatus } from '../../../../shared/types'

// The main-window half of the bar↔main chat bridge. The bar is a VIEWPORT over
// the ONE chat engine (INV-CHAT-1 / Mac INV-6): the app's single useChat lives in
// AppStateProvider, and this host — mounted once inside it, main-window only —
// (1) drives that engine when the bar sends (bar:sendChat → chat.send), and
// (2) broadcasts the engine's projected state back to the bar (chat:state), so
// the bar renders the same thread Home shows, with no second useChat instance
// (the old duplicate that dropped PTT messages from Home — bug C3).
//
// Streaming updates history on every SSE chunk; publishes are throttled (~50ms
// trailing) so the IPC/serialization cost stays bounded during a fast reply.
const PUBLISH_THROTTLE_MS = 50

export function ChatBridgeHost(): null {
  const { chat } = useAppState()
  const { history, sending, speaking } = chat

  const status: BarChatStatus = speaking ? 'speaking' : sending ? 'sending' : 'idle'
  // The projected snapshot the bar renders. Held in a ref so the pull path
  // (bar:requestChatState) and the throttled publisher always read fresh values.
  const stateRef = useRef<BarChatState>({ messages: history, sending, status })
  // eslint-disable-next-line react-hooks/refs -- latest-ref: the pull path + throttled publisher read the freshest snapshot
  stateRef.current = { messages: history, sending, status }

  const publish = useCallback((): void => {
    window.omi?.publishChatState?.(stateRef.current)
  }, [])

  // Serialize sends so a back-to-back voice message isn't dropped while the
  // previous reply is still streaming (useChat.send no-ops a re-entrant call).
  const sendRef = useRef(chat.send)
  // eslint-disable-next-line react-hooks/refs -- latest-ref: the once-registered bar listener must call the newest send
  sendRef.current = chat.send
  const sendChainRef = useRef<Promise<void>>(Promise.resolve())

  useEffect(() => {
    return window.omi?.onBarChatSend?.(({ text, fromVoice }) => {
      sendChainRef.current = sendChainRef.current
        .then(() => sendRef.current(text, { fromVoice }))
        .catch(() => {})
    })
  }, [])

  // The bar pulls state on mount / each reveal — answer with the current snapshot.
  useEffect(() => {
    return window.omi?.onBarRequestChatState?.(() => publish())
  }, [publish])

  // Throttled broadcast on every state change (leading + trailing at 50ms).
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastAtRef = useRef(0)
  useEffect(() => {
    const since = Date.now() - lastAtRef.current
    const fire = (): void => {
      lastAtRef.current = Date.now()
      timerRef.current = null
      publish()
    }
    if (since >= PUBLISH_THROTTLE_MS) fire()
    else if (timerRef.current === null)
      timerRef.current = setTimeout(fire, PUBLISH_THROTTLE_MS - since)
  }, [history, sending, status, publish])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return null
}
