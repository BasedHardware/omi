import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Mic, Monitor, Send } from 'lucide-react'
import type { User } from 'firebase/auth'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { useAppState } from '../state/AppStateProvider'
import { Markdown } from '../components/Markdown'
import { maybeBuildLocalGraph } from '../lib/kgSynthesis'
import { cn } from '../lib/utils'
import omiMark from '../assets/omi-logo.png'
import { maybeStartScreenSynthesis } from '../lib/screenSynthesis'
import { maybeStartInsightEngine } from '../lib/insightEngine'
import { maybeStartRetentionSweep } from '../lib/retentionSweep'
import { getPreferences, onPreferencesChange, setPreferences } from '../lib/preferences'
import type { RewindSettings } from '../../../shared/types'

function firstName(u: User | null): string {
  const display = u?.displayName?.trim().split(/\s+/)[0]
  if (display) return display
  const emailLocal = u?.email?.split('@')[0]
  return emailLocal || 'there'
}

const FADE_MASK = 'linear-gradient(to bottom, transparent 0px, #000 190px)'

function ChatBar(props: {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  sending: boolean
  micOn: boolean
  screenOn: boolean
  onToggleMic: () => void
  onToggleScreen: () => void
  screenDisabled: boolean
}): React.JSX.Element {
  const toolButton = (
    label: string,
    Icon: typeof Mic,
    active: boolean,
    onClick: () => void,
    disabled = false
  ): React.JSX.Element => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={cn(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-all duration-200 disabled:opacity-40',
        active
          ? 'bg-white/[0.08] text-white shadow-[0_0_18px_rgba(91,2,224,0.55)]'
          : 'text-white/45 hover:bg-white/[0.06] hover:text-white/80'
      )}
    >
      <Icon className="h-5 w-5" strokeWidth={active ? 2.25 : 1.9} />
    </button>
  )

  return (
    <div className="flex min-h-[4.7rem] items-center gap-2 rounded-full border border-white/12 bg-black/35 px-5 py-2.5 shadow-[0_16px_50px_rgba(0,0,0,0.28)] backdrop-blur-xl">
      <input
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') props.onSend()
        }}
        placeholder="Ask Omi..."
        className="min-w-0 flex-1 border-0 bg-transparent px-2 py-3 text-[1.05rem] text-white placeholder:text-white/40 focus:outline-none focus:ring-0"
      />
      {toolButton(
        'Screen recording',
        Monitor,
        props.screenOn,
        props.onToggleScreen,
        props.screenDisabled
      )}
      {toolButton('Microphone', Mic, props.micOn, props.onToggleMic)}
      <div className="mx-1 h-8 w-px bg-white/10" />
      <button
        disabled={props.sending}
        onClick={props.onSend}
        aria-label="Send"
        title="Send"
        className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white/[0.12] text-white/85 transition-colors hover:bg-white/[0.18] hover:text-white disabled:opacity-50"
      >
        <Send className="h-5 w-5" strokeWidth={2} />
      </button>
    </div>
  )
}

export function Home(): React.JSX.Element {
  const { chat } = useAppState()
  const [user, setUser] = useState<User | null>(auth.currentUser)
  const chatScrollRef = useRef<HTMLDivElement>(null)
  const lastLenRef = useRef(0)

  const PAGE_SIZE = 30
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const restoreFromBottom = useRef<number | null>(null)
  const nearBottomRef = useRef(true)
  const [overflowing, setOverflowing] = useState(false)

  const started = chat.history.length > 0
  const photoURL = user?.photoURL
  const initial = (user?.displayName || user?.email)?.[0]?.toUpperCase() ?? '?'

  const [input, setInput] = useState('')
  const handleSend = (): void => {
    const text = input
    if (!text.trim() || chat.sending) return
    setInput('')
    void chat.send(text)
  }

  const [micOn, setMicOn] = useState<boolean>(() => !!getPreferences().continuousRecording)
  const [rewind, setRewind] = useState<RewindSettings | null>(null)

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])
  useEffect(() => onPreferencesChange((p) => setMicOn(!!p.continuousRecording)), [])
  useEffect(() => {
    void window.omi.rewindGetSettings().then(setRewind)
    return window.omi.onRewindSettings(setRewind)
  }, [])

  const toggleMic = (): void => {
    setPreferences({ continuousRecording: !getPreferences().continuousRecording })
  }

  const toggleScreen = (): void => {
    if (!rewind) return
    const next = { ...rewind, captureEnabled: !rewind.captureEnabled }
    setRewind(next)
    void window.omi.rewindSetSettings(next).then(setRewind)
  }

  useEffect(() => {
    const t = setTimeout(() => void maybeBuildLocalGraph(), 1800)
    maybeStartScreenSynthesis()
    maybeStartInsightEngine()
    maybeStartRetentionSweep()
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    const el = chatScrollRef.current
    if (!el) return
    const isNewMessage = chat.history.length !== lastLenRef.current
    lastLenRef.current = chat.history.length
    if (isNewMessage || nearBottomRef.current) {
      el.style.scrollBehavior = isNewMessage ? 'smooth' : 'auto'
      el.scrollTop = el.scrollHeight
      nearBottomRef.current = true
    }
    setOverflowing(el.scrollHeight > el.clientHeight + 4)
  }, [chat.history, chat.sending])

  const onThreadScroll = (): void => {
    const el = chatScrollRef.current
    if (!el) return
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    setOverflowing(el.scrollHeight > el.clientHeight + 4)
    if (el.scrollTop < 80 && visibleCount < chat.history.length) {
      restoreFromBottom.current = el.scrollHeight - el.scrollTop
      setVisibleCount((n) => Math.min(n + PAGE_SIZE, chat.history.length))
    }
  }

  useLayoutEffect(() => {
    const el = chatScrollRef.current
    if (!el || restoreFromBottom.current == null) return
    el.scrollTop = el.scrollHeight - restoreFromBottom.current
    restoreFromBottom.current = null
  }, [visibleCount])

  const mask = overflowing ? FADE_MASK : undefined
  const windowStart = Math.max(0, chat.history.length - visibleCount)
  const windowed = chat.history.slice(windowStart)

  return (
    <div className="flex h-full flex-col px-6 pb-9 pt-28 lg:px-10">
      <div
        ref={chatScrollRef}
        onScroll={onThreadScroll}
        className="min-h-0 flex-1 overflow-y-auto"
        style={{ WebkitMaskImage: mask, maskImage: mask }}
      >
        <div
          className={cn(
            'mx-auto flex min-h-full w-full max-w-4xl flex-col',
            started ? 'justify-end' : 'justify-center'
          )}
        >
          <div className="space-y-2 pb-3">
            {started ? (
              windowed.map((m, i) => {
                const isUser = m.role === 'user'
                const isLast = i === windowed.length - 1
                return (
                  <div
                    key={m.id ?? `${windowStart}-${i}`}
                    className={cn('flex items-end gap-2.5', isUser && 'flex-row-reverse')}
                  >
                    {isUser ? (
                      <div className="relative h-7 w-7 shrink-0 overflow-hidden rounded-full border border-white/10">
                        <img
                          src={photoURL ?? ''}
                          alt=""
                          className={cn(
                            'h-full w-full object-cover',
                            photoURL ? 'block' : 'hidden'
                          )}
                          referrerPolicy="no-referrer"
                          onError={(e) => {
                            const el = e.currentTarget
                            el.classList.add('hidden')
                            el.nextElementSibling?.classList.remove('hidden')
                          }}
                        />
                        <div
                          className={cn(
                            'flex h-full w-full items-center justify-center bg-white/10 text-[11px] font-semibold text-white',
                            photoURL ? 'hidden' : ''
                          )}
                        >
                          {initial}
                        </div>
                      </div>
                    ) : (
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white">
                        <img src={omiMark} alt="Omi" className="h-4 w-4 object-contain" />
                      </div>
                    )}
                    <div
                      className={cn(
                        'bubble-in w-fit max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-snug',
                        isUser
                          ? 'rounded-br-md bg-[color:var(--accent)] text-right text-white'
                          : 'rounded-bl-md bg-white/[0.06] text-left text-white/80'
                      )}
                    >
                      {isUser ? (
                        <div className="whitespace-pre-wrap">{m.content}</div>
                      ) : (
                        <Markdown text={m.content || (chat.sending && isLast ? '...' : '')} />
                      )}
                    </div>
                  </div>
                )
              })
            ) : (
              <h1 className="fade-in-slow text-center font-display text-5xl font-semibold tracking-tight text-white">
                Hi, {firstName(user)}
              </h1>
            )}
          </div>
        </div>
      </div>

      <div className="shrink-0 py-3">
        <div className="fade-in-slow mx-auto w-full max-w-4xl">
          <ChatBar
            value={input}
            onChange={setInput}
            onSend={handleSend}
            sending={chat.sending}
            micOn={micOn}
            screenOn={!!rewind?.captureEnabled}
            screenDisabled={!rewind}
            onToggleMic={toggleMic}
            onToggleScreen={toggleScreen}
          />
        </div>
      </div>
    </div>
  )
}
