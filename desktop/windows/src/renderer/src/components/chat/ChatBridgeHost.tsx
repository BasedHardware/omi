import { useCallback, useEffect, useRef } from 'react'
import { useAppState } from '../../state/appState'
import { interruptCurrentResponse } from '../../lib/voice/voiceController'
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

// Backstop for the "wait until the engine is idle before delivering a queued bar
// send" loop. It bounds only ORDINARY streams (chat replies are seconds); a
// delegated coding-agent task legitimately holds the engine for MINUTES and is
// exempted (see waitUntilEngineIdle), so this cap never truncates one.
const ENGINE_IDLE_WAIT_CAP_MS = 60_000

export function ChatBridgeHost(): null {
  const { chat } = useAppState()
  const { history, sending, speaking, agentActive } = chat

  const status: BarChatStatus = speaking ? 'speaking' : sending ? 'sending' : 'idle'
  // The projected snapshot the bar renders. Held in a ref so the pull path
  // (bar:requestChatState) and the throttled publisher always read fresh values.
  const stateRef = useRef<BarChatState>({
    messages: history,
    sending,
    status,
    agentsActive: agentActive
  })
  // eslint-disable-next-line react-hooks/refs -- latest-ref: the pull path + throttled publisher read the freshest snapshot
  stateRef.current = { messages: history, sending, status, agentsActive: agentActive }

  const publish = useCallback((): void => {
    window.omi?.publishChatState?.(stateRef.current)
  }, [])

  // Serialize sends so a back-to-back voice message isn't dropped while the
  // previous reply is still streaming (useChat.send no-ops a re-entrant call).
  const sendRef = useRef(chat.send)
  // eslint-disable-next-line react-hooks/refs -- latest-ref: the once-registered bar listener must call the newest send
  sendRef.current = chat.send
  const sendChainRef = useRef<Promise<void>>(Promise.resolve())
  // Latest-ref mirrors of the engine's busy signals so the stable bar-send
  // listener can tell when the shared engine is busy — and whether it's busy on a
  // long-running coding-agent task (which must not be truncated by the cap).
  const sendingStateRef = useRef(sending)
  // eslint-disable-next-line react-hooks/refs -- latest-ref: the send chain reads the freshest sending flag
  sendingStateRef.current = sending
  const agentActiveStateRef = useRef(agentActive)
  // eslint-disable-next-line react-hooks/refs -- latest-ref: the send chain reads the freshest agent-active flag
  agentActiveStateRef.current = agentActive

  // Defer a bar send until the shared engine is idle. useChat.send() no-ops a
  // re-entrant call via a PRIVATE latch the bridge can't observe, so a bar/PTT
  // message that lands while a Home-initiated send is still streaming would be
  // dropped silently — the C3 message-loss class, across surfaces. Waiting for
  // `sending` to clear ENQUEUES it instead; sendRef always points at the newest
  // send, so the deferred call runs against fresh history.
  //
  // A delegated coding-agent task holds the engine busy for MINUTES; it is
  // exempted from the cap (agentActive) so the queued send is never truncated
  // mid-task and dropped. The cap bounds only an ordinary stream so a wedged SSE
  // can't block the bar's send queue forever; if it ever fires we log (bounded +
  // observable — never a silent drop).
  const waitUntilEngineIdle = useCallback((): Promise<void> => {
    if (!sendingStateRef.current) return Promise.resolve()
    return new Promise<void>((resolve) => {
      const startedAt = Date.now()
      const iv = setInterval(() => {
        const busy = sendingStateRef.current
        const wedged =
          !agentActiveStateRef.current && Date.now() - startedAt > ENGINE_IDLE_WAIT_CAP_MS
        if (!busy || wedged) {
          clearInterval(iv)
          if (busy && wedged) {
            console.warn(
              '[ChatBridgeHost] engine still busy after cap — delivering the queued bar send anyway'
            )
          }
          resolve()
        }
      }, 50)
    })
  }, [])

  useEffect(() => {
    return window.omi?.onBarChatSend?.(({ text, fromVoice }) => {
      sendChainRef.current = sendChainRef.current
        .then(() => waitUntilEngineIdle())
        .then(() => sendRef.current(text, { fromVoice }))
        .catch(() => {})
    })
  }, [waitUntilEngineIdle])

  // The bar pulls state on mount / each reveal — answer with the current snapshot.
  useEffect(() => {
    return window.omi?.onBarRequestChatState?.(() => publish())
  }, [publish])

  // Barge-in: a bar PTT hold started → stop Omi's still-playing spoken reply.
  // Playback lives here (main window) in the voiceController singleton useChat
  // speaks through, so this is the surface that can actually interrupt it.
  useEffect(() => {
    return window.omi?.onBarChatInterrupt?.(() => interruptCurrentResponse())
  }, [])

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
  }, [history, sending, status, agentActive, publish])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return null
}
