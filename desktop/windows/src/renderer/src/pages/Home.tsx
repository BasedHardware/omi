import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import type { User } from 'firebase/auth'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { useAppState } from '../state/AppStateProvider'
import { QuickTaskWidget } from '../components/home/QuickTaskWidget'
import { QuickGoalsWidget } from '../components/home/QuickGoalsWidget'
import { Markdown } from '../components/Markdown'
import { maybeBuildLocalGraph } from '../lib/kgSynthesis'
import { cn } from '../lib/utils'
import omiMark from '../assets/omi-logo.png'
import { maybeStartScreenSynthesis } from '../lib/screenSynthesis'
import { maybeStartInsightEngine } from '../lib/insightEngine'
import { maybeStartRetentionSweep } from '../lib/retentionSweep'

function firstName(u: User | null): string {
  const display = u?.displayName?.trim().split(/\s+/)[0]
  if (display) return display
  const emailLocal = u?.email?.split('@')[0]
  return emailLocal || 'there'
}

// Bubbles dissolve across the top ~190px of the thread (only once it overflows),
// so they fade out before reaching the widgets above.
const FADE_MASK = 'linear-gradient(to bottom, transparent 0px, #000 190px)'

// 5 grid rows: [topSpacer][widgets][middle][bar][bottomSpacer]. Only the
// SPACERS and the MIDDLE ever change, and they're all `fr` — the widgets and bar
// rows stay `auto` the whole time. That matters: Chromium can't smoothly
// interpolate an `auto` track, so every animated track must be `fr` to avoid the
// glitchy jump. Idle = one centered block; on the first message BOTH spacers
// collapse together so the widgets and the bar land at the edges at the same time.
const ROWS_IDLE = '1fr auto minmax(0, 0.8fr) auto 1fr'
const ROWS_FULL = '0fr auto minmax(0, 1fr) auto 0fr'

function ChatBar(props: {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  sending: boolean
}): React.JSX.Element {
  // Solid (no backdrop-blur): a blurred bar re-rasterizes every frame during the
  // bar's slide, which made that transition feel laggy.
  return (
    <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-[color:var(--surface)] px-3 py-1.5">
      <input
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') props.onSend()
        }}
        placeholder="Ask Omi…"
        className="flex-1 border-0 bg-transparent px-2 py-2 text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-0"
      />
      <button
        disabled={props.sending}
        onClick={props.onSend}
        aria-label="Send"
        className="shrink-0 rounded-xl bg-white/[0.06] p-2.5 text-white/80 transition-colors hover:bg-white/[0.12] hover:text-white disabled:opacity-50"
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  )
}

export function Home(): React.JSX.Element {
  const { chat } = useAppState()
  const [user, setUser] = useState<User | null>(auth.currentUser)
  const chatScrollRef = useRef<HTMLDivElement>(null)
  const widgetsGridRef = useRef<HTMLDivElement>(null)
  const lastLenRef = useRef(0)

  // Windowed history rendering: an infinite thread can hold thousands of
  // messages, so we only render the last `visibleCount` and reveal older ones a
  // page at a time as the user scrolls to the top. This keeps the DOM small
  // while the whole thread stays accessible. `restoreFromBottom` holds the
  // distance-from-bottom captured right before a page grows, so the layout
  // effect can restore the scroll position (no jump) once the older bubbles
  // mount above.
  const PAGE_SIZE = 30
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const restoreFromBottom = useRef<number | null>(null)
  // Whether the view is currently near the bottom. Used to decide if a streaming
  // reply / cross-window update should keep the view pinned to the bottom, or
  // leave it put because the user has scrolled up to read older history. Starts
  // true so the initial load lands at the bottom.
  const nearBottomRef = useRef(true)

  // Measured natural height of the widgets grid. The widget row animates its
  // height from 0 → this once BOTH widgets' data is ready, so they appear
  // together and slide the chat smoothly — no per-widget pop-in / reshuffle.
  const [widgetsH, setWidgetsH] = useState(0)
  const [tasksReady, setTasksReady] = useState(false)
  const [goalsReady, setGoalsReady] = useState(false)
  const widgetsReady = tasksReady && goalsReady

  // Only fade the thread's top once it actually overflows — otherwise a short
  // thread would sit entirely inside the fade and look washed out.
  const [overflowing, setOverflowing] = useState(false)
  // Split layout: false = idle (centered block), true = widgets at top + bar at
  // bottom. A small lead-in lets the first bubble render before the move starts
  // (avoids a glitchy instant jump); both spacers then collapse together so the
  // widgets and the bar land at the screen edges at the same time.
  const [split, setSplit] = useState(false)
  // Bubbles wait until the bar has reached the bottom, so the first message
  // doesn't pop in mid-slide.
  const [showThread, setShowThread] = useState(false)

  const started = chat.history.length > 0
  const photoURL = user?.photoURL
  const initial = (user?.displayName || user?.email)?.[0]?.toUpperCase() ?? '?'

  // Draft text is LOCAL state (not in the app-wide chat hook) so typing only
  // re-renders Home's chat bar — not the whole app shell + every mounted page.
  const [input, setInput] = useState('')
  const handleSend = (): void => {
    const text = input
    if (!text.trim() || chat.sending) return
    setInput('')
    void chat.send(text)
  }

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])

  // Lazily (re)build the local knowledge graph in the background — deferred past
  // the entrance animations so its DB/synthesis work can't stall them.
  useEffect(() => {
    const t = setTimeout(() => void maybeBuildLocalGraph(), 1800)
    maybeStartScreenSynthesis()
    maybeStartInsightEngine()
    maybeStartRetentionSweep()
    return () => clearTimeout(t)
  }, [])

  // Safety net: reveal the widgets after a few seconds even if a fetch never
  // resolves, so they can't hang invisible.
  useEffect(() => {
    const t = setTimeout(() => {
      setTasksReady(true)
      setGoalsReady(true)
    }, 6000)
    return () => clearTimeout(t)
  }, [])

  // Measure the widgets grid's natural height so the row can animate its height
  // (0 → this) when both are ready — sliding the chat box rather than jumping it.
  useEffect(() => {
    const el = widgetsGridRef.current
    if (!el) return
    const check = (): void => setWidgetsH(el.offsetHeight)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Drive the staggered split once a conversation starts: lead-in → bar down →
  // widgets up. Resets to centered if the thread is ever cleared.
  useEffect(() => {
    if (!started) {
      setSplit(false)
      setShowThread(false)
      return
    }
    const t1 = setTimeout(() => setSplit(true), 150)
    // Reveal the thread only after the split (lead-in + 1000ms transition) lands.
    const t2 = setTimeout(() => setShowThread(true), 150 + 1000)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [started])

  // Pin the thread to the bottom. Smooth-scroll on a NEW message (so existing
  // bubbles glide up to make room); instant while a reply streams in.
  // `showThread` is a dep so that on app startup — where infinite-mode history
  // loads async and the thread only mounts after the split animation (showThread
  // flips ~1150ms later) — this fires once the bubbles actually render and lands
  // the view at the bottom instead of the top.
  // `widgetsReady`/`widgetsH` are deps because the Tasks/Goals row pops from
  // height 0 → full height instantly when both load (often a beat after the chat
  // first paints), which shrinks the thread viewport from the top and would
  // otherwise leave the view scrolled up. Re-pin (only if the reader is near the
  // bottom) so the latest message stays in view when the widgets land.
  useEffect(() => {
    const el = chatScrollRef.current
    if (!el) return
    const isNewMessage = chat.history.length !== lastLenRef.current
    lastLenRef.current = chat.history.length
    // Pin to the bottom on a new message or the first reveal, but while a reply
    // streams in (content grows without the count changing) only keep pinning if
    // the user is already near the bottom — otherwise leave them where they
    // scrolled to read older history instead of yanking them down.
    if (isNewMessage || nearBottomRef.current) {
      el.style.scrollBehavior = isNewMessage ? 'smooth' : 'auto'
      el.scrollTop = el.scrollHeight
      nearBottomRef.current = true
    }
    setOverflowing(el.scrollHeight > el.clientHeight + 4)
  }, [chat.history, chat.sending, showThread, widgetsReady, widgetsH])

  // Reveal an older page when the user scrolls near the top, capturing the
  // current distance-from-bottom so the view can be pinned in place afterward.
  const onThreadScroll = (): void => {
    const el = chatScrollRef.current
    if (!el) return
    // Track whether we're near the bottom so the pin effect knows whether a
    // streaming reply should keep following or leave the reader in place.
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    setOverflowing(el.scrollHeight > el.clientHeight + 4)
    if (el.scrollTop < 80 && visibleCount < chat.history.length) {
      restoreFromBottom.current = el.scrollHeight - el.scrollTop
      setVisibleCount((n) => Math.min(n + PAGE_SIZE, chat.history.length))
    }
  }

  // After an older page mounts, restore the scroll position so the content the
  // user was reading stays put instead of jumping. Runs before paint.
  useLayoutEffect(() => {
    const el = chatScrollRef.current
    if (!el || restoreFromBottom.current == null) return
    el.scrollTop = el.scrollHeight - restoreFromBottom.current
    restoreFromBottom.current = null
  }, [visibleCount])

  const mask = overflowing ? FADE_MASK : undefined

  // Render only the tail of the thread; older messages reveal on scroll-up.
  const windowStart = Math.max(0, chat.history.length - visibleCount)
  const windowed = chat.history.slice(windowStart)

  return (
    <div
      className="grid h-full px-6 py-8 transition-[grid-template-rows] duration-[1000ms] ease-[cubic-bezier(0.4,0,0.2,1)] lg:px-10"
      style={{ gridTemplateRows: split ? ROWS_FULL : ROWS_IDLE }}
    >
      {/* Top spacer (collapses as the conversation starts). */}
      <div aria-hidden />

      {/* Widgets row — its height grows smoothly (0 → measured) when data loads,
          so the chat box slides to make room instead of jumping. Each card also
          fades in via widget-fade. */}
      {/* The row's height is set instantly (no layout animation) once both
          widgets are ready; the reveal itself is a compositor-only transform +
          opacity fade, so it can't reflow/jank the way animating height did. */}
      <div className="overflow-hidden" style={{ height: widgetsReady ? widgetsH + 48 : 0 }}>
        <div
          className={cn(
            'transition-[transform,opacity] duration-[600ms] ease-[cubic-bezier(0.4,0,0.2,1)] will-change-transform',
            widgetsReady ? 'translate-y-0 opacity-100' : '-translate-y-3 opacity-0'
          )}
        >
          <div
            ref={widgetsGridRef}
            className="mx-auto grid w-full max-w-4xl items-stretch gap-4 sm:grid-cols-2"
          >
            <QuickTaskWidget onReady={() => setTasksReady(true)} />
            <QuickGoalsWidget onReady={() => setGoalsReady(true)} />
          </div>
          <div className="h-12" />
        </div>
      </div>

      {/* Middle: the thread (active) or the greeting (idle). */}
      <div
        ref={chatScrollRef}
        onScroll={onThreadScroll}
        className="min-h-0 overflow-y-auto"
        style={{ WebkitMaskImage: mask, maskImage: mask }}
      >
        <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col">
          <div className="mt-auto space-y-2 pb-2">
            {started && showThread ? (
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
                          className={cn('h-full w-full object-cover', photoURL ? 'block' : 'hidden')}
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
                        <Markdown
                          text={m.content || (chat.sending && isLast ? '…' : '')}
                        />
                      )}
                    </div>
                  </div>
                )
              })
            ) : !started ? (
              <h1 className="fade-in-slow pb-2 text-center font-display text-4xl font-semibold tracking-tight text-white">
                Hi, {firstName(user)}
              </h1>
            ) : null}
          </div>
        </div>
      </div>

      {/* Chat bar — rides to the bottom via the spacer collapse. */}
      <div className="py-3">
        <div className="fade-in-slow mx-auto max-w-4xl">
          <ChatBar value={input} onChange={setInput} onSend={handleSend} sending={chat.sending} />
        </div>
      </div>

      {/* Bottom spacer (collapses as the conversation starts). */}
      <div aria-hidden />
    </div>
  )
}
