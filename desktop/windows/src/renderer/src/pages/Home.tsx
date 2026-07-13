import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, AudioLines } from 'lucide-react'
import type { User } from 'firebase/auth'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { useAppState } from '../state/appState'
import { QuickTaskWidget } from '../components/home/QuickTaskWidget'
import { QuickGoalsWidget } from '../components/home/QuickGoalsWidget'
import { RevealMarkdown } from '../components/chat/RevealMarkdown'
import { maybeBuildLocalGraph } from '../lib/kgSynthesis'
import { cn } from '../lib/utils'
import { keepLastPositive } from '../lib/measure'
import omiMark from '../assets/omi-mark.png'
import { maybeStartScreenSynthesis } from '../lib/screenSynthesis'
import { maybeStartInsightEngine } from '../lib/insightEngine'
import { maybeStartRetentionSweep } from '../lib/retentionSweep'
import { VoiceSessionSurface } from '../components/voice/VoiceSessionSurface'

function firstName(u: User | null): string {
  const display = u?.displayName?.trim().split(/\s+/)[0]
  if (display) return display
  const emailLocal = u?.email?.split('@')[0]
  return emailLocal || 'there'
}

// Bubbles dissolve across the top ~190px of the thread (only once it overflows),
// so they fade out before reaching the widgets above.
const FADE_MASK = 'linear-gradient(to bottom, transparent 0px, #000 190px)'
type ChatScrollMode = 'followingBottom' | 'freeScrolling'

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
  voiceOpen: boolean
  onToggleVoice: () => void
}): React.JSX.Element {
  const canSend = props.value.trim().length > 0 && !props.sending
  // Solid (no backdrop-blur): a blurred bar re-rasterizes every frame during the
  // bar's slide, which made that transition feel laggy.
  return (
    <div className="flex items-center gap-1.5 rounded-section border border-line bg-[color:var(--surface)] py-1.5 pl-4 pr-1.5 shadow-[0_10px_28px_rgba(0,0,0,0.28)] transition-colors duration-200 focus-within:border-line-strong">
      <input
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') props.onSend()
        }}
        placeholder="Ask Omi…"
        className="flex-1 border-0 bg-transparent py-2 pr-2 text-[15px] text-white placeholder:text-white/35 focus:outline-none focus:ring-0"
      />
      <button
        onClick={props.onToggleVoice}
        aria-label={props.voiceOpen ? 'Hide voice session' : 'Talk with Omi'}
        className={cn(
          'shrink-0 rounded-full p-2.5 transition-colors duration-150',
          props.voiceOpen
            ? 'bg-white/[0.14] text-white'
            : 'text-white/60 hover:bg-white/[0.08] hover:text-white'
        )}
      >
        <AudioLines className="h-4 w-4" />
      </button>
      {/* Send is THE primary action: white fill + dark glyph once there is
          something to send, quiet until then. */}
      <button
        disabled={!canSend}
        onClick={props.onSend}
        aria-label="Send"
        className={cn(
          'shrink-0 rounded-full p-2.5 transition-all duration-150',
          canSend
            ? 'bg-[color:var(--accent)] text-[color:var(--accent-contrast)] hover:opacity-90'
            : 'bg-white/[0.06] text-white/40'
        )}
      >
        <ArrowUp className="h-4 w-4" strokeWidth={2.25} />
      </button>
    </div>
  )
}

export function Home(): React.JSX.Element {
  const { chat } = useAppState()
  const [user, setUser] = useState<User | null>(auth.currentUser)
  const chatScrollRef = useRef<HTMLDivElement>(null)
  const chatContentRef = useRef<HTMLDivElement>(null)
  const widgetsGridRef = useRef<HTMLDivElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const lastLenRef = useRef(0)
  const [scrollMode, setScrollModeState] = useState<ChatScrollMode>('followingBottom')
  const scrollModeRef = useRef<ChatScrollMode>('followingBottom')
  const isProgrammaticScrollRef = useRef(false)
  const pendingScrollFrameRef = useRef<number | null>(null)

  const setScrollMode = useCallback((mode: ChatScrollMode): void => {
    scrollModeRef.current = mode
    setScrollModeState(mode)
  }, [])

  const cancelPendingScroll = useCallback((): void => {
    if (pendingScrollFrameRef.current == null) return
    window.cancelAnimationFrame(pendingScrollFrameRef.current)
    pendingScrollFrameRef.current = null
  }, [])

  const scrollToLatest = useCallback(
    (opts: { smooth?: boolean; force?: boolean } = {}): void => {
      const { smooth = false, force = false } = opts
      const el = chatScrollRef.current
      if (!el) return
      if (!force && scrollModeRef.current !== 'followingBottom') return

      cancelPendingScroll()
      pendingScrollFrameRef.current = window.requestAnimationFrame(() => {
        pendingScrollFrameRef.current = null
        const currentEl = chatScrollRef.current
        if (!currentEl) return
        if (!force && scrollModeRef.current !== 'followingBottom') return
        isProgrammaticScrollRef.current = true
        currentEl.style.scrollBehavior = smooth ? 'smooth' : 'auto'
        currentEl.scrollTop = currentEl.scrollHeight
        window.requestAnimationFrame(() => {
          isProgrammaticScrollRef.current = false
        })
      })
    },
    [cancelPendingScroll]
  )

  const resumeFollowing = useCallback(
    (smooth = true): void => {
      setScrollMode('followingBottom')
      scrollToLatest({ smooth, force: true })
    },
    [scrollToLatest, setScrollMode]
  )

  const releaseFollowing = useCallback((): void => {
    cancelPendingScroll()
    isProgrammaticScrollRef.current = false
    setScrollMode('freeScrolling')
  }, [cancelPendingScroll, setScrollMode])

  // Release following only when the reader actually scrolls AWAY from the live
  // edge. A downward wheel at the bottom (no movement) must NOT release, and
  // plain mouse clicks must NOT release (they are not scroll intent). This
  // avoids breaking live-follow on no-op input. Used for onWheel/onTouchMove.
  const releaseFollowingIfScrolledAway = useCallback(
    (e?: React.WheelEvent | WheelEvent): void => {
      const el = chatScrollRef.current
      if (!el) return
      // If we're still at/near the bottom, check wheel direction: an upward
      // wheel (deltaY < 0) is reader intent to leave the live edge and should
      // release following even though the browser hasn't applied the delta yet.
      // A downward wheel at the bottom is a no-op; don't release.
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      if (distFromBottom <= 8) {
        // At/near bottom — only release on explicit upward wheel intent, and
        // only if the thread actually overflows (short threads can't scroll
        // away, so an upward wheel is a no-op that shouldn't release following).
        if (e && 'deltaY' in e && e.deltaY < 0 && el.scrollHeight > el.clientHeight + 8) {
          releaseFollowing()
        }
        return
      }
      releaseFollowing()
    },
    [releaseFollowing]
  )

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
  // The thread overflows (and the top fade shows) once its content is taller than
  // the viewport. Recomputed from several effects/handlers, so it lives in one spot.
  const recomputeOverflow = useCallback((): void => {
    const el = chatScrollRef.current
    if (el) setOverflowing(el.scrollHeight > el.clientHeight + 4)
  }, [])
  // Split layout: false = idle (centered block), true = widgets at top + bar at
  // bottom. A small lead-in lets the first bubble render before the move starts
  // (avoids a glitchy instant jump); both spacers then collapse together so the
  // widgets and the bar land at the screen edges at the same time.
  const [split, setSplit] = useState(false)
  // Bubbles wait until the bar has reached the bottom, so the first message
  // doesn't pop in mid-slide.
  const [showThread, setShowThread] = useState(false)

  const started = chat.history.length > 0
  // The top cards persist on every VISIT to Home — they show on mount even when
  // a conversation already exists — and stay until the user clicks any area
  // below them (the thread or the chat bar), which dismisses them for this visit
  // only. `cardsDismissed` is per-visit interaction state; a fresh visit re-arms
  // it (see the IntersectionObserver below — Home is kept-alive, never
  // unmounted, so we can't lean on unmount to reset). Dismissal also drops the
  // thread's top fade so the chat reads at full focus.
  const [cardsDismissed, setCardsDismissed] = useState(false)
  const widgetsVisible = widgetsReady && !cardsDismissed
  const dismissCards = useCallback((): void => setCardsDismissed(true), [])

  // Draft text is LOCAL state (not in the app-wide chat hook) so typing only
  // re-renders Home's chat bar — not the whole app shell + every mounted page.
  const [input, setInput] = useState('')
  // Voice-session surface (Phase 6), toggled from the chat bar. The surface
  // component is host-agnostic — the Phase 4 bar mounts the same one later.
  const [voiceOpen, setVoiceOpen] = useState(false)
  const handleSend = (): void => {
    const text = input
    if (!text.trim() || chat.sending) return
    setInput('')
    resumeFollowing(true)
    void chat.send(text)
  }

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])

  useEffect(() => () => cancelPendingScroll(), [cancelPendingScroll])

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
    // Ignore 0-height reads via keepLastPositive: when Home is navigated away
    // from it is hidden with display:none (see MainViews' panelClass), which
    // makes the ResizeObserver fire a 0×0 rect. Writing that 0 would clobber the
    // cached height, so on return React would paint the (un-transitioned) widget
    // row at 48px and then snap to the real height a frame later — the
    // intermittent "quick glitch". Keeping the last real measurement makes the
    // return render correct up front.
    const check = (): void => setWidgetsH((prev) => keepLastPositive(prev, el.offsetHeight))
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Home is kept-alive by MainViews — it toggles a `hidden` class on Home's
  // WRAPPER (see MainViews.panelClass), never unmounting Home — so per-visit
  // state like `cardsDismissed` can't reset on unmount. Watch that wrapper's
  // class directly: each hidden→visible flip is a fresh visit, so re-arm the
  // cards. A MutationObserver on the exact attribute that changes is
  // deterministic (an IntersectionObserver threshold callback proved unreliable
  // on the display:none flip); and it avoids re-rendering this heavy panel on
  // every unrelated navigation the way useLocation would.
  useEffect(() => {
    const panel = rootRef.current?.parentElement
    if (!panel) return
    let wasHidden = panel.classList.contains('hidden')
    const mo = new MutationObserver(() => {
      const isHidden = panel.classList.contains('hidden')
      if (wasHidden && !isHidden) setCardsDismissed(false)
      wasHidden = isHidden
    })
    mo.observe(panel, { attributes: true, attributeFilter: ['class'] })
    return () => mo.disconnect()
  }, [])

  // Drive the staggered split once a conversation starts: lead-in → bar down →
  // widgets up. Resets to centered if the thread is ever cleared.
  useEffect(() => {
    if (!started) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional load-on-mount / reset-on-dependency-change; not a self-retriggering loop
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

  // Follow live output only while the reader is following the live edge.
  // Physical wheel/touch scroll releases following; geometry/layout changes
  // (stream growth, widget height, Markdown rendering) do not count as intent.
  useEffect(() => {
    const el = chatScrollRef.current
    if (!el) return
    const previousLen = lastLenRef.current
    const isNewMessage = chat.history.length !== previousLen
    const isInitialReveal = previousLen === 0 && chat.history.length > 0
    lastLenRef.current = chat.history.length

    if (isInitialReveal || scrollModeRef.current === 'followingBottom') {
      scrollToLatest({ smooth: isNewMessage && !isInitialReveal })
    }
    recomputeOverflow()
  }, [
    chat.history,
    chat.sending,
    showThread,
    scrollToLatest,
    recomputeOverflow,
    widgetsReady,
    widgetsH
  ])

  // RevealMarkdown grows the streaming reply's text every 16ms WITHOUT a
  // chat.history change, so the effect above (keyed on history) can't follow it.
  // Mirror BarChatSurface: observe the thread content and re-pin the live edge on
  // every size change while following, so the bottom tracks the char-by-char
  // reveal smoothly instead of jumping once per SSE chunk.
  useEffect(() => {
    const content = chatContentRef.current
    if (!content) return
    const ro = new ResizeObserver(() => {
      recomputeOverflow()
      if (scrollModeRef.current === 'followingBottom') scrollToLatest()
    })
    ro.observe(content)
    return () => ro.disconnect()
  }, [scrollToLatest, recomputeOverflow])

  // Reveal an older page when the user scrolls near the top, capturing the
  // current distance-from-bottom so the view can be pinned in place afterward.
  const onThreadScroll = (): void => {
    const el = chatScrollRef.current
    if (!el) return
    recomputeOverflow()
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distFromBottom <= 8) {
      // Resume live following when the reader scrolls back to the live edge.
      if (scrollModeRef.current !== 'followingBottom') {
        setScrollMode('followingBottom')
      }
    } else if (scrollModeRef.current === 'followingBottom' && !isProgrammaticScrollRef.current) {
      // Release following when the viewport moves away from the live edge via
      // a non-programmatic scroll (scrollbar thumb drag, keyboard arrows, etc).
      // onWheel/onTouchMove already cover wheel/touch; this covers the rest.
      setScrollMode('freeScrolling')
    }
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

  // Drop the top fade once the cards are dismissed — with nothing above the
  // thread to tuck under, the chat reads at full focus.
  const mask = overflowing && !cardsDismissed ? FADE_MASK : undefined

  // Render only the tail of the thread; older messages reveal on scroll-up.
  const windowStart = Math.max(0, chat.history.length - visibleCount)
  const windowed = chat.history.slice(windowStart)

  return (
    <div
      ref={rootRef}
      className="grid h-full px-6 py-8 transition-[grid-template-rows] duration-[1000ms] ease-[cubic-bezier(0.4,0,0.2,1)] lg:px-10"
      style={{ gridTemplateRows: split ? ROWS_FULL : ROWS_IDLE }}
    >
      {/* Top spacer (collapses as the conversation starts). */}
      <div aria-hidden />

      {/* Widgets row — its height grows smoothly (0 → measured) when data loads,
          so the chat box slides to make room instead of jumping. Each card also
          fades in via widget-fade. */}
      {/* On REVEAL the height is set instantly (no layout animation) once both
          widgets are ready; the reveal itself is a compositor-only transform +
          opacity fade, so it can't reflow/jank the way animating height did. On
          DISMISS (a click below the cards) the row collapses the other way — the
          height IS transitioned to 0 (only while dismissed, so reveal/return
          stay instant), tucked together with the 600ms fade so the cards leave
          as one coherent motion. */}
      <div
        data-testid="widgets-row"
        className={cn(
          'overflow-hidden',
          cardsDismissed && 'transition-[height] duration-[600ms] ease-[cubic-bezier(0.4,0,0.2,1)]'
        )}
        style={{ height: widgetsVisible ? widgetsH + 48 : 0 }}
      >
        <div
          className={cn(
            'transition-[transform,opacity] duration-[600ms] ease-[cubic-bezier(0.4,0,0.2,1)] will-change-transform',
            widgetsVisible ? 'translate-y-0 opacity-100' : '-translate-y-3 opacity-0'
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

      {/* Middle: the thread (active) or the greeting (idle). The scroller is
          wrapped in a relative container so the Latest overlay is a sibling of
          the scroller — an absolute child of a scrolled element moves with the
          scrollable content and can scroll out of the visible viewport. */}
      {/* Dismiss hitbox: the thread/greeting region is "below the cards", so a
          mousedown anywhere in it tucks the cards away (see also the chat bar
          and bottom spacer). Mousedown (not click) so a press-drag select or a
          scrollbar grab counts too. */}
      <div className="relative min-h-0" data-testid="chat-below-region" onMouseDown={dismissCards}>
        <div
          ref={chatScrollRef}
          onScroll={onThreadScroll}
          onWheel={(e) => releaseFollowingIfScrolledAway(e)}
          onTouchMove={() => releaseFollowingIfScrolledAway()}
          className="h-full overflow-y-auto"
          style={{ WebkitMaskImage: mask, maskImage: mask }}
        >
          <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col">
            <div ref={chatContentRef} className="mt-auto space-y-5 pb-2">
              {started && showThread ? (
                windowed.map((m, i) => {
                  const isUser = m.role === 'user'
                  const isLast = i === windowed.length - 1
                  if (isUser) {
                    // User turn: white accent bubble, no avatar (iMessage-style —
                    // the right alignment already says "you").
                    return (
                      <div key={m.id ?? `${windowStart}-${i}`} className="flex justify-end">
                        <div className="bubble-in w-fit max-w-[75%] whitespace-pre-wrap rounded-[18px] rounded-br-[6px] bg-[color:var(--accent)] px-4 py-2.5 text-[15px] leading-snug text-[color:var(--accent-contrast)]">
                          {m.content}
                        </div>
                      </div>
                    )
                  }
                  // Assistant turn: omi mark + open text on the canvas (no bubble)
                  // so replies read like a document, not a widget.
                  return (
                    <div
                      key={m.id ?? `${windowStart}-${i}`}
                      className="bubble-in flex items-start gap-3"
                    >
                      {/* Crisp 256px omi mark (omi-mark.png) clipped to the
                          circle. overflow-hidden is load-bearing: it guarantees
                          the asset's SQUARE bounds can never poke past the round
                          badge (the old 40px omi-logo.png had opaque-white
                          corners whose diagonal exceeded the badge radius → four
                          corner bumps). The mark is rendered larger than the
                          badge (h-14 in an h-11 badge) to offset the asset's
                          ~23% built-in padding, so the dot-ring reads at ~30px. */}
                      <div className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white">
                        <img src={omiMark} alt="Omi" className="h-14 w-14 object-contain" />
                      </div>
                      {/* pt-3 (12px) optically centers the first reply line on
                          the 44px badge: Inter 15px/24.75px puts the first line's
                          cap-midline ~12.4px below the text-box top, so a 12px
                          top pad lands it at ~24px = the badge's vertical center
                          (measured live: badge centerY 648 vs first-line ~638
                          before, ~648 after). Tuned to the badge size — revisit
                          if the badge height changes. */}
                      <div className="min-w-0 max-w-[85%] pt-3 text-[15px] leading-[1.65] text-white/90">
                        {m.content ? (
                          <RevealMarkdown
                            text={m.content}
                            startRevealed={!(isLast && chat.sending)}
                          />
                        ) : chat.sending && isLast ? (
                          <span className="typing-dots" aria-label="Omi is replying">
                            <span />
                            <span />
                            <span />
                          </span>
                        ) : null}
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
        {scrollMode === 'freeScrolling' && started ? (
          <button
            type="button"
            aria-label="Jump to latest message"
            onClick={() => resumeFollowing(true)}
            className="absolute bottom-4 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-line-strong bg-[color:var(--bg-raised)] px-3.5 py-2 text-sm font-medium text-white shadow-[0_8px_24px_rgba(0,0,0,0.35)] transition-colors hover:bg-[color:var(--bg-tertiary)]"
          >
            <ArrowDown className="h-4 w-4" />
            Latest
          </button>
        ) : null}
      </div>

      {/* Chat bar — rides to the bottom via the spacer collapse. Also "below the
          cards": engaging the input/voice dismisses them for this visit. */}
      <div className="py-3" onMouseDown={dismissCards}>
        <div className="fade-in-slow mx-auto max-w-4xl">
          {voiceOpen && (
            <div className="mb-2">
              <VoiceSessionSurface onClose={() => setVoiceOpen(false)} />
            </div>
          )}
          <ChatBar
            value={input}
            onChange={setInput}
            onSend={handleSend}
            sending={chat.sending}
            voiceOpen={voiceOpen}
            onToggleVoice={() => setVoiceOpen((v) => !v)}
          />
        </div>
      </div>

      {/* Bottom spacer (collapses as the conversation starts) — still "below the
          cards", so clicking it dismisses them too. */}
      <div aria-hidden onMouseDown={dismissCards} />
    </div>
  )
}
