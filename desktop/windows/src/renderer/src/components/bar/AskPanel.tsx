// The bar's expanded content — the ask/chat surface MIGRATED from the old
// overlay window's OverlayPanel (the overlay folded into the bar; one surface,
// not two). Chat lifetime, send serialization, PTT wiring, and the streaming
// scroll-pin behavior are unchanged; the drag handle is gone (the bar is
// anchored to the top edge) and the panel reports its PTT machine + activity
// upward so the bar can drive the orb and main can drive hotkey-hold PTT.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useChat } from '../../hooks/useChat'
import { usePushToTalk } from '../../hooks/usePushToTalk'
import { Waveform } from '../overlay/Waveform'
import { ChatMessages } from '../chat/ChatMessages'
import type { WaveformSource } from '../../../../shared/types'

export type AskPanelActivity = {
  recording: boolean
  transcribing: boolean
  sending: boolean
  /** Resolve the live PTT analyser at sample time (it attaches shortly AFTER
   *  `recording` flips true — a snapshot would be stale-null). */
  getAnalyser: () => WaveformSource | null
}

export type AskPanelProps = {
  /** Hand the PTT gesture handle up (main's summon-hold drives it via IPC). */
  onRegisterPtt?: (handle: { beginHold: () => void; endHold: () => void }) => void
  /** Live activity for the orb (speaking/thinking states + amplitude source). */
  onActivity?: (activity: AskPanelActivity) => void
  /** Close button — the bar collapses/hides (same as the shortcut). */
  onClose: () => void
}

export function AskPanel({ onRegisterPtt, onActivity, onClose }: AskPanelProps): React.JSX.Element {
  const { history, sending, send, reset } = useChat({ surface: 'overlay' })
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)

  // Serialize sends so a back-to-back voice message isn't fired while the previous
  // reply is still streaming (which `useChat.send` would no-op). Each send is
  // chained after the prior one resolves and dispatched through the latest `send`.
  const sendRef = useRef(send)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref (reads newest value in once-registered listeners, avoids stale closures)
  sendRef.current = send
  const sendChainRef = useRef<Promise<void>>(Promise.resolve())
  // Whether the message list should stay pinned to the live edge (see the
  // ResizeObserver pin effect below).
  const followRef = useRef(true)
  const enqueueSend = useCallback((text: string): void => {
    // Single send choke-point (typed Enter + voice commit) — tell onboarding the
    // user asked something in the bar.
    window.omiOverlay.notifyAsked()
    // Asking something = wanting to see the answer: re-engage bottom-following
    // even if the reader had scrolled up earlier.
    followRef.current = true
    sendChainRef.current = sendChainRef.current.then(() => sendRef.current(text)).catch(() => {})
  }, [])

  // Latest draft, read by the window-level (textarea-unfocused) push-to-talk path.
  const draftRef = useRef(draft)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref
  draftRef.current = draft

  const ptt = usePushToTalk({
    onTranscript: (text) => setDraft(text),
    onCommit: (text) => enqueueSend(text),
    // Fires on every completed hold capture, even when transcription was
    // unavailable — drives the onboarding voice step.
    onCaptureEnd: () => window.omiOverlay.notifyVoiceCaptured(),
    restoreDraft: (snapshot) => setDraft(snapshot),
    getDraft: () => draftRef.current
  })

  // Expose the PTT gesture handle + live activity to the bar shell.
  const registerRef = useRef(onRegisterPtt)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref
  registerRef.current = onRegisterPtt
  const beginHoldRef = useRef(ptt.beginHold)
  const endHoldRef = useRef(ptt.endHold)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref
  beginHoldRef.current = ptt.beginHold
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref
  endHoldRef.current = ptt.endHold
  useEffect(() => {
    registerRef.current?.({
      beginHold: () => beginHoldRef.current(),
      endHold: () => endHoldRef.current()
    })
  }, [])
  const analyserRefStable = ptt.analyserRef
  useEffect(() => {
    onActivity?.({
      recording: ptt.recording,
      transcribing: ptt.transcribing,
      sending,
      getAnalyser: () => analyserRefStable.current
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- analyserRef is a stable ref
  }, [ptt.recording, ptt.transcribing, sending])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Auto-grow the input to fit its contents — especially the live voice
  // transcript, which streams into `draft`.
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  // Keep the message list pinned to the bottom while streaming — but only
  // while the reader is AT the live edge (scrolling up disengages the pin;
  // returning to the bottom re-engages it).
  const hasHistory = history.length > 0
  useEffect(() => {
    const el = scrollRef.current
    const content = messagesRef.current
    if (!el || !content) return
    const pin = (): void => {
      if (followRef.current) el.scrollTop = el.scrollHeight
    }
    pin()
    const ro = new ResizeObserver(pin)
    ro.observe(content)
    const onWheel = (e: WheelEvent): void => {
      if (e.deltaY < 0 && el.scrollHeight > el.clientHeight + 8) followRef.current = false
    }
    const onScroll = (): void => {
      if (el.scrollHeight - el.scrollTop - el.clientHeight <= 8) followRef.current = true
    }
    el.addEventListener('wheel', onWheel, { passive: true })
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      ro.disconnect()
      el.removeEventListener('wheel', onWheel)
      el.removeEventListener('scroll', onScroll)
    }
  }, [hasHistory])

  // Each summon: refocus the input. History survives hide/show (no remount).
  useEffect(() => {
    return window.omiOverlay.onShown(() => {
      inputRef.current?.focus()
    })
  }, [])

  // Esc: while recording OR finalizing, abort the capture (don't send).
  // Otherwise reset the chat to a fresh thread in place. Esc never closes the
  // bar — closing is the global shortcut / the ✕ button, which keep history.
  const onKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (ptt.recording || ptt.transcribing) {
        ptt.cancel()
      } else {
        reset()
        setDraft('')
      }
    }
  }

  const submit = (): void => {
    const text = draft.trim()
    if (!text) return
    setDraft('')
    enqueueSend(text)
  }

  return (
    <div onKeyDown={onKeyDown} className="flex flex-col text-neutral-100">
      <button
        onClick={onClose}
        aria-label="Close"
        title="Close (same as the shortcut)"
        className="absolute right-2.5 top-2 z-10 flex h-5 w-5 items-center justify-center rounded-md text-xs leading-none text-neutral-500 transition-colors hover:bg-neutral-700/50 hover:text-neutral-200"
      >
        ✕
      </button>

      <div className="flex min-h-0 flex-col gap-3 px-4 pb-4 pt-8">
        {history.length > 0 && (
          <div
            ref={scrollRef}
            // Fixed cap; past it the list scrolls internally, pinned to the
            // bottom. The bar window is a fixed-size transparent canvas, so no
            // window-height feedback loop exists here (unlike the old overlay).
            className="max-h-[340px] min-h-0 overflow-y-auto pr-1"
          >
            <div ref={messagesRef} className="space-y-2">
              <ChatMessages messages={history} sending={sending} variant="overlay" />
            </div>
          </div>
        )}

        <div className="flex shrink-0 flex-col gap-2">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              rows={1}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // Push-to-talk gets first dibs on Space; if it consumes the
                // event, skip the Enter/typing path.
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
              disabled={sending || ptt.recording || ptt.transcribing || !draft.trim()}
              className="rounded-xl bg-neutral-200 px-3 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
            >
              Send
            </button>
          </div>

          {ptt.recording && (
            <div
              data-testid="ptt-listening"
              className="flex items-center gap-3 rounded-xl bg-neutral-800/50 px-3 py-1.5"
            >
              <span className="shrink-0 text-xs font-medium text-neutral-300">Listening…</span>
              <Waveform analyserRef={ptt.analyserRef} />
              <span className="shrink-0 text-[10px] text-neutral-500">
                release to send · Esc cancels
              </span>
            </div>
          )}

          {!ptt.recording && ptt.transcribing && (
            <div
              data-testid="ptt-transcribing"
              className="flex items-center gap-2 rounded-xl bg-neutral-800/50 px-3 py-1.5"
            >
              <div className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-neutral-600 border-t-neutral-200" />
              <span className="shrink-0 text-xs font-medium text-neutral-300">Transcribing…</span>
              <span className="shrink-0 text-[10px] text-neutral-500">Esc cancels</span>
            </div>
          )}

          {!ptt.recording && !ptt.transcribing && ptt.hint && (
            <div
              data-testid="ptt-hint"
              className="flex items-center gap-2 rounded-xl bg-neutral-800/50 px-3 py-1.5"
            >
              <span className="shrink-0 text-xs font-medium text-neutral-300">{ptt.hint}</span>
            </div>
          )}
        </div>

        {ptt.error && !ptt.recording && (
          <div data-testid="ptt-error" className="px-1 text-[11px] text-red-400">
            Voice: {ptt.error}
          </div>
        )}
      </div>
    </div>
  )
}
