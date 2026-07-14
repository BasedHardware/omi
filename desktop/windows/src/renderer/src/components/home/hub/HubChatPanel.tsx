import { useEffect, useRef } from 'react'
import { ChatMessages } from '../../chat/ChatMessages'
import type { ChatMsg } from '../../../hooks/useChat'

// The chat stage. It renders the app's ONE chat engine (useAppState().chat) through
// the SAME shared ChatMessages the legacy Home and the bar use — no second thread
// implementation, no second message array (INV-CHAT-1).
//
// `children` is the ask bar, re-docked at the panel's foot: the Hub has a single
// input element that MOVES between the stage and the panel, so the draft survives
// the transition instead of being retyped into a second bar.

export function HubChatPanel(props: {
  messages: ChatMsg[]
  sending: boolean
  children: React.ReactNode
}): React.JSX.Element {
  const { messages, sending, children } = props
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  // Pin the live edge. RevealMarkdown grows the streaming reply's text WITHOUT a
  // history change, so watching `messages` alone would lag the reveal by a chunk —
  // observe the content box and re-pin on every size change (mirrors BarChatSurface).
  useEffect(() => {
    const content = contentRef.current
    if (!content) return
    const pin = (): void => {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
    }
    pin()
    const ro = new ResizeObserver(pin)
    ro.observe(content)
    return () => ro.disconnect()
  }, [])

  return (
    <div
      className="flex h-full w-full flex-col rounded-[26px] border p-5"
      style={{
        borderColor: 'rgb(var(--home-stage-glow-rgb) / 0.14)',
        backgroundImage:
          'linear-gradient(to bottom, rgb(255 255 255 / 0.03), rgb(var(--home-stage-glow-rgb) / 0.05))',
        boxShadow: '0 18px 44px rgb(0 0 0 / 0.42)'
      }}
    >
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div ref={contentRef} className="flex flex-col gap-3">
          <ChatMessages messages={messages} sending={sending} variant="main" />
        </div>
      </div>
      <div className="pt-[22px]">{children}</div>
    </div>
  )
}
