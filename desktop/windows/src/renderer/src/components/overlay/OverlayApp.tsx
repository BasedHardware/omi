// src/renderer/src/components/overlay/OverlayApp.tsx
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useChat } from '../../hooks/useChat'
import { useAuth } from '../../hooks/useAuth'
import { usePushToTalk } from '../../hooks/usePushToTalk'
import { auth } from '../../lib/firebase'
import { Waveform } from './Waveform'
import { ChatMessages } from '../chat/ChatMessages'
import './overlay.css'

/** Slim draggable strip with a centered grab handle. The whole strip is a drag
 *  region (-webkit-app-region: drag); the handle just signals that it's movable. */
function DragHandle(): React.JSX.Element {
  return (
    <div className="overlay-drag flex h-6 items-center justify-center">
      <div className="h-1 w-8 rounded-full bg-neutral-600/60" />
    </div>
  )
}

/** Inner panel: one useChat lifetime == one thread. It stays mounted across
 *  hide/show so chat history persists within a session; Esc resets the thread in
 *  place (useChat.reset) and replays the entrance animation via `replayEnter`. */
function OverlayPanel({ replayEnter }: { replayEnter: () => void }): React.JSX.Element {
  const { history, sending, send, reset } = useChat({ surface: 'overlay' })
  const [draft, setDraft] = useState('')
  const [leaving, setLeaving] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)

  // Serialize sends so a back-to-back voice message isn't fired while the previous
  // reply is still streaming (which `useChat.send` would no-op). Each send is
  // chained after the prior one resolves and dispatched through the latest `send`.
  const sendRef = useRef(send)
  sendRef.current = send
  const sendChainRef = useRef<Promise<void>>(Promise.resolve())
  const enqueueSend = useCallback((text: string): void => {
    // Single send choke-point (typed Enter + voice commit) — tell onboarding the
    // user asked something in the bar.
    window.omiOverlay.notifyAsked()
    sendChainRef.current = sendChainRef.current.then(() => sendRef.current(text)).catch(() => {})
  }, [])

  // Hold-Space-to-talk: a quick Space tap types a space; holding past the threshold
  // records mic audio, renders the live transcript into the box, and on release
  // auto-sends it (queued behind any in-flight reply).
  // Latest draft, read by the window-level (textarea-unfocused) push-to-talk path.
  const draftRef = useRef(draft)
  draftRef.current = draft

  const ptt = usePushToTalk({
    onTranscript: (text) => setDraft(text),
    onCommit: (text) => {
      setDraft('')
      enqueueSend(text)
    },
    // Fires on every completed hold-Space capture, even when transcription was
    // unavailable (quota/1008) or silent. Drives the onboarding voice step so a
    // no-quota account can finish onboarding instead of being stuck waiting for a
    // transcript that will never arrive.
    onCaptureEnd: () => window.omiOverlay.notifyVoiceCaptured(),
    restoreDraft: (snapshot) => setDraft(snapshot),
    getDraft: () => draftRef.current
  })

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Auto-grow the input to fit its contents — especially the live voice transcript,
  // which streams into `draft`. Without this the rows={1} textarea shows only the
  // first line (the rest scrolls out of view), so a long transcript looks truncated
  // even though it's all captured. Grows up to the CSS max-height, then scrolls; the
  // overlay window follows via its ResizeObserver on the shell.
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  // Keep the message list pinned to the bottom. A `history` dep alone misses the
  // gradual text reveal + bubble-in growth (the height changes WITHOUT a new array
  // reference), so the view fell behind a streaming reply. A ResizeObserver on the
  // messages wrapper re-pins on EVERY height change — new message, streamed chunk,
  // or animation — so the latest line is always visible. Re-binds when the scroll
  // container mounts (it only renders once there's history).
  const hasHistory = history.length > 0
  useEffect(() => {
    const el = scrollRef.current
    const content = messagesRef.current
    if (!el || !content) return
    const pin = (): void => {
      el.scrollTop = el.scrollHeight
    }
    pin()
    const ro = new ResizeObserver(pin)
    ro.observe(content)
    return () => ro.disconnect()
  }, [hasHistory])

  // Each summon: refocus the input and clear any leftover `leaving` (overlay-leave)
  // state from the close animation. The entrance fade itself is driven by the shell
  // in OverlayApp, so the history survives hide/show without a remount.
  useEffect(() => {
    return window.omiOverlay.onShown(() => {
      setLeaving(false)
      inputRef.current?.focus()
    })
  }, [])

  const dismiss = (): void => {
    setLeaving(true)
    window.setTimeout(() => window.omiOverlay.hide(), 140)
  }

  // Esc: while recording OR finalizing, abort the capture (don't send). Otherwise
  // reset the chat to a fresh thread in place and replay the entrance animation. Esc
  // never closes the overlay — closing is the global shortcut / the ✕ button, which
  // keep history.
  const onKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (ptt.recording || ptt.finalizing) {
        ptt.cancel()
      } else {
        reset()
        setDraft('')
        replayEnter()
      }
    }
  }

  const submit = (): void => {
    const text = draft.trim()
    if (!text) return
    setDraft('')
    // Queue (don't drop) so pressing Enter while a reply is still streaming sends
    // the next message right after it finishes.
    enqueueSend(text)
  }

  return (
    <div
      onKeyDown={onKeyDown}
      className={`overlay-panel relative ${leaving ? 'overlay-leave' : ''} flex flex-col text-neutral-100`}
    >
      <DragHandle />
      <button
        onClick={dismiss}
        aria-label="Close"
        title="Close (same as the shortcut)"
        className="overlay-no-drag absolute right-2 top-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-md text-xs leading-none text-neutral-500 transition-colors hover:bg-neutral-700/50 hover:text-neutral-200"
      >
        ✕
      </button>

      <div className="flex min-h-0 flex-col gap-3 px-4 pb-4">
        {history.length > 0 && (
          <div
            ref={scrollRef}
            // Grows with the messages on screen (the window follows via the
            // ResizeObserver), capped at a fixed height — past that the list scrolls,
            // pinned to the bottom so the latest exchange stays visible. NOT a vh cap:
            // vh is the window's own height, which is derived from this content, so a
            // vh cap is a feedback loop that both starves the height (you'd see ~1
            // message) and oscillates while growing (the glitch). main also clamps the
            // window to 70% of the screen as a backstop.
            className="overlay-no-drag max-h-[360px] min-h-0 overflow-y-auto pr-1"
          >
            <div ref={messagesRef} className="space-y-2">
              <ChatMessages messages={history} sending={sending} variant="overlay" />
            </div>
          </div>
        )}

        {/* shrink-0: the window height tweens to catch up to grown content, so for a
            frame the content is taller than the window; without this the input (the
            last flex child) gets shrunk/clipped and looks like it disappears after a
            send. Pinning it means the history above shrinks/scrolls instead. */}
        <div className="overlay-no-drag flex shrink-0 flex-col gap-2">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              rows={1}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // Push-to-talk gets first dibs on Space; if it consumes the event,
                // skip the Enter/typing path.
                if (ptt.onKeyDown(e)) return
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  submit()
                }
              }}
              onKeyUp={(e) => ptt.onKeyUp(e)}
              placeholder="Ask Omi…  ·  hold Space to talk"
              className="max-h-32 flex-1 resize-none rounded-xl bg-neutral-800/70 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:ring-1 focus:ring-neutral-500"
            />
            <button
              onClick={submit}
              disabled={sending || ptt.recording || ptt.finalizing || !draft.trim()}
              className="rounded-xl bg-neutral-200 px-3 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
            >
              Send
            </button>
          </div>

          {ptt.recording && (
            // Live capture strip BELOW the input, ONLY while holding Space: the
            // waveform animates and the recognized transcript renders into the
            // textarea above. On release the strip disappears (no "Transcribing…");
            // the transcript keeps filling the box and auto-sends when settled.
            <div className="flex items-center gap-3 rounded-xl bg-neutral-800/50 px-3 py-1.5">
              <span className="shrink-0 text-xs font-medium text-neutral-300">Listening…</span>
              <Waveform analyserRef={ptt.analyserRef} />
              <span className="shrink-0 text-[10px] text-neutral-500">
                release to send · Esc cancels
              </span>
            </div>
          )}
        </div>

        {ptt.error && !ptt.recording && (
          <div className="px-1 text-[11px] text-red-400">Voice: {ptt.error}</div>
        )}
      </div>
    </div>
  )
}

/** Signed-out card: never crash, surface the main window to sign in. */
function SignedOutPanel(): React.JSX.Element {
  return (
    <div className="overlay-panel flex flex-col text-neutral-100">
      <DragHandle />
      <div className="flex flex-col items-center gap-3 px-6 pb-6 pt-1 text-center">
        <div className="text-sm text-neutral-300">Sign in to Omi to chat.</div>
        <button
          onClick={() => window.omiOverlay.focusMain()}
          className="overlay-no-drag rounded-xl bg-neutral-200 px-4 py-2 text-sm font-medium text-neutral-900"
        >
          Open Omi to sign in
        </button>
      </div>
    </div>
  )
}

/** Brief card shown while auth resolves. Never reported to main as "ready", so the
 *  window doesn't show until the real (signed-in/out) content exists. */
function LoadingPanel(): React.JSX.Element {
  return (
    <div className="overlay-panel flex flex-col text-neutral-100">
      <DragHandle />
      <div className="px-4 pb-4 text-sm text-neutral-400">Loading…</div>
    </div>
  )
}

export function OverlayApp(): React.JSX.Element {
  const { user, loading } = useAuth()
  const [authReady, setAuthReady] = useState(false)
  const shellRef = useRef<HTMLDivElement | null>(null)

  // Stage the shell hidden as early as possible — a ref callback runs during commit,
  // before the first paint — so the window never flashes the fully-opaque panel
  // before the entrance fade runs.
  const setShellRef = useCallback((node: HTMLDivElement | null) => {
    shellRef.current = node
    if (node) node.style.opacity = '0'
  }, [])

  // Fade + scale the whole shell in. Driven imperatively (Web Animations API) so it
  // replays on each summon without remounting — remounting would wipe the chat
  // history we keep for the session. Clears the inline opacity on finish so the
  // panel rests at its CSS opacity (1).
  const playEnter = useCallback((): void => {
    const el = shellRef.current
    if (!el) return
    el.style.opacity = '0'
    const anim = el.animate(
      [
        { opacity: 0, transform: 'scale(0.97) translateY(-4px)' },
        { opacity: 1, transform: 'scale(1) translateY(0)' }
      ],
      { duration: 150, easing: 'ease-out' }
    )
    anim.onfinish = () => {
      el.style.opacity = ''
    }
  }, [])

  // Transparent page background so the native window material shows through.
  useEffect(() => {
    document.body.classList.add('overlay-body')
    return () => document.body.classList.remove('overlay-body')
  }, [])

  // Track window focus via main (reliable BrowserWindow focus/blur): when the
  // window is inactive, Win11 brightens the acrylic backdrop, so we darken the
  // wash (overlay.css `.overlay-inactive`) to keep it dark + translucent in rest
  // mode instead of showing the OS's bright inactive tint.
  useEffect(() => {
    const setInactive = (v: boolean): void => {
      document.body.classList.toggle('overlay-inactive', v)
    }
    setInactive(!document.hasFocus())
    return window.omiOverlay.onActiveChange((active) => setInactive(!active))
  }, [])

  // Wait for Firebase to finish resolving persistence before deciding signed-in
  // vs signed-out, so the sign-in card can't flash on load.
  useEffect(() => {
    let active = true
    void auth.authStateReady().then(() => {
      if (active) setAuthReady(true)
    })
    return () => {
      active = false
    }
  }, [])

  const ready = !loading && authReady

  // Report content height to main so it can size the window — but only once the
  // REAL content (signed-in or signed-out) is mounted, never the loading card. The
  // first report flips the window to "ready" and triggers the DEFERRED first show
  // at the correct height (main/window.ts), so no empty/oversized frame flashes.
  // The ResizeObserver then keeps main in sync as the reply/history grows.
  useLayoutEffect(() => {
    if (!ready) return
    const el = shellRef.current
    if (!el) return
    const report = (): void => window.omiOverlay.setHeight(el.offsetHeight + 2)
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ready])

  // Play the entrance fade on each summon; pre-stage the shell hidden right before a
  // hide so the next summon fades in cleanly instead of flashing the opaque panel.
  useEffect(() => window.omiOverlay.onShown(() => playEnter()), [playEnter])
  useEffect(
    () =>
      window.omiOverlay.onWillHide(() => {
        const el = shellRef.current
        if (el) el.style.opacity = '0'
      }),
    []
  )

  let content: React.JSX.Element
  if (!ready) content = <LoadingPanel />
  else if (!user) content = <SignedOutPanel />
  else content = <OverlayPanel replayEnter={playEnter} />

  // The measured/animated shell wraps a zoom layer (overlay.css `.overlay-zoom`)
  // that lays the panel out at the original width and paints it at 50% — scaling
  // layout AND fonts uniformly. Because the zoom is on a CHILD, shell.offsetHeight
  // already reports the halved height, so the window auto-sizes to it.
  return (
    <div ref={setShellRef}>
      <div className="overlay-zoom">{content}</div>
    </div>
  )
}
