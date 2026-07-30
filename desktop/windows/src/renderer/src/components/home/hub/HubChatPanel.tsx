import { useRef } from 'react'
import { ChatMessages } from '../../chat/ChatMessages'
import { useLiveEdgeFollow } from '../../../hooks/useLiveEdgeFollow'
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
  // Optional row rendered above the scroll area (the multi-chat header). Renders
  // nothing when omitted, so the default single-thread panel is unchanged.
  header?: React.ReactNode
  children: React.ReactNode
}): React.JSX.Element {
  const { messages, sending, header, children } = props
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  // Pin the live edge while the reply streams, releasing as soon as the reader
  // scrolls up to read earlier messages (shared with the bar surfaces).
  useLiveEdgeFollow(scrollRef, contentRef)

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
      {header}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div ref={contentRef} className="flex min-h-full flex-col gap-3">
          {messages.length === 0 && !sending ? (
            // The panel opens on ask-bar FOCUS (Mac does this: clicking the bar
            // reveals the inline chat). On Mac the thread persists, so it almost
            // always has something in it — but Windows defaults chatHistoryMode to
            // 'per-launch', so on a fresh launch the very same transition would
            // otherwise reveal a large, empty, glowing box. Give the empty thread
            // something to say instead of rendering a void.
            <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
              <p className="text-[15px] font-medium text-home-ink">Ask omi anything</p>
              <p className="max-w-sm text-[13px] text-home-muted">
                It can see your conversations, tasks, memories, and screen history.
              </p>
            </div>
          ) : (
            <ChatMessages messages={messages} sending={sending} variant="main" />
          )}
        </div>
      </div>
      <div className="pt-[22px]">{children}</div>
    </div>
  )
}
