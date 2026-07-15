// The top-edge bar renderer (#/bar) — the shell inside the fixed transparent
// window. Owns the reveal motion (slide-in from the edge), the pill ⇄ panel
// morph (ONE surface element interpolating size + radius — never a crossfade of
// two components), the interactive-island hit-testing handshake, and the orb
// wired to real state.
//
// The bar chat is a VIEWPORT over the main window's single chat engine
// (INV-CHAT-1): this renderer holds NO useChat. Sends go out via the bridge
// (window.omiBar.sendChat), and projected state (history + streaming + status)
// arrives via window.omiBar.onChatState. Expanded surface = a chat LIST that
// opens the conversation inline (BarChatSurface).
//
// PTT: the push-to-talk machine is mounted here (always alive) so a hotkey HOLD
// captures regardless of which surface is showing. A hold reveals the PILL and
// drives the orb only — no transcript text, no waveform bars (the orb is the
// sole status indicator). On release the bar STAYS a pill; the reply is spoken.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useAuth } from '../../hooks/useAuth'
import { auth } from '../../lib/firebase'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import { usePushToTalk } from '../../hooks/usePushToTalk'
import { useCodingAgents } from '../../hooks/useCodingAgents'
import { Orb } from '../orb/Orb'
import { BarChatSurface } from './BarChatSurface'
import { createBarSender } from './barSend'
import {
  deriveOrbState,
  isBarBusy,
  deriveAgentRows,
  pillLabel,
  nextConversationDraft,
  type BarAgentRow
} from './barDisplay'
import type {
  BarMode,
  BarShowPayload,
  BarChatState,
  CodingAgentId,
  WaveformSource
} from '../../../../shared/types'
import './bar.css'

const PILL = { width: 148, height: 36 }
const PANEL_WIDTH = 336
// The expanded panel content is laid out at 480px and painted at 0.7 (bar-zoom),
// matching the established bar density. Heights measured through it are in these
// pre-zoom units; the factor lets us bound the message list to the window (C4).
const PANEL_ZOOM = 0.7
// Grace after a voice exchange fully ends (playback drained) before the pill is
// allowed to retract — long enough that a spoken answer doesn't vanish instantly.
const RETRACT_GRACE_MS = 1800

const EMPTY_CHAT: BarChatState = { messages: [], sending: false, status: 'idle' }

function SignedOutContent(): React.JSX.Element {
  return (
    <div className="flex flex-col items-center gap-3 px-6 pb-5 pt-6 text-center text-neutral-100">
      <div className="text-sm text-neutral-300">Sign in to Omi to chat.</div>
      <button
        onClick={() => window.omiOverlay.focusMain()}
        className="rounded-xl bg-neutral-200 px-4 py-2 text-sm font-medium text-neutral-900"
      >
        Open Omi to sign in
      </button>
    </div>
  )
}

export function BarApp(): React.JSX.Element {
  const { user, loading } = useAuth()
  const [authReady, setAuthReady] = useState(false)
  const [mode, setMode] = useState<BarMode | null>(null)
  const [sliding, setSliding] = useState<'in' | 'out'>('out')
  const [genesisNonce, setGenesisNonce] = useState(0)
  const [continuous, setContinuous] = useState(() => !!getPreferences().continuousRecording)
  // Speak replies to TYPED bar questions too (macOS
  // floatingBarTypedQuestionVoiceAnswersEnabled, default off). PTT/voice replies
  // are always spoken regardless; this only governs typed submits below.
  const [typedVoice, setTypedVoice] = useState(
    () => !!getPreferences().floatingBarTypedVoiceEnabled
  )
  const [chat, setChat] = useState<BarChatState>(EMPTY_CHAT)
  // Connected coding agents (shared fetch with Settings → Agents).
  const { agents } = useCodingAgents()
  // Which adapter is running the current task (the shared engine only projects a
  // single global agentsActive; agent_selected names the adapter). At most one
  // row shows "Working…".
  const [activeAgentId, setActiveAgentId] = useState<CodingAgentId | null>(null)
  const [view, setView] = useState<'list' | 'conversation'>('list')
  // Which row the open conversation belongs to: null = the Omi Chat thread, else
  // the coding-agent row that opened it (drives the header title + draft seed).
  // The engine + history stay one shared thread (INV-CHAT-1) — this only steers
  // the entry framing so "Claude Code" no longer opens a view titled "Omi Chat".
  const [target, setTarget] = useState<BarAgentRow | null>(null)
  const [draft, setDraft] = useState('')
  const modeRef = useRef<BarMode | null>(null)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for IPC listeners
  modeRef.current = mode
  const draftRef = useRef(draft)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the PTT machine
  draftRef.current = draft
  const panelInnerRef = useRef<HTMLDivElement>(null)
  const [panelHeight, setPanelHeight] = useState(120)

  // Transparent page background (the window has no material).
  useEffect(() => {
    document.body.classList.add('bar-body')
    return () => document.body.classList.remove('bar-body')
  }, [])

  useEffect(() => onPreferencesChange((p) => setContinuous(!!p.continuousRecording)), [])
  useEffect(() => onPreferencesChange((p) => setTypedVoice(!!p.floatingBarTypedVoiceEnabled)), [])
  useEffect(() => {
    let active = true
    void auth.authStateReady().then(() => {
      if (active) setAuthReady(true)
    })
    return () => {
      active = false
    }
  }, [])

  // --- chat viewport (projected from the main window) -------------------------
  // Every bar send — typed submit AND PTT commit — goes through the usage-limit
  // gate (barSend.ts). A refused send never reaches the engine; it returns the
  // limit line, which the bar shows inline while the main window raises the
  // shared popup (and speaks it back for a voice turn). The quota is a cached
  // snapshot, refreshed on mount + each reveal, so the send path stays off the
  // network.
  const [sender] = useState(() => createBarSender())
  const [limitNotice, setLimitNotice] = useState<string | null>(null)
  // Resolves to the blocked-limit notice (null when the send went out) so the
  // typed surface can put the user's words back in the input instead of eating
  // them — a refused send never lands in the transcript.
  const sendFromBar = useCallback(
    async (text: string, fromVoice: boolean): Promise<string | null> => {
      const notice = await sender.send(text, fromVoice)
      setLimitNotice(notice)
      return notice
    },
    [sender]
  )
  useEffect(() => {
    void sender.sync()
  }, [sender])
  useEffect(() => window.omiBar.onChatState((s) => setChat(s)), [])
  // Pull the current thread on mount (in case we missed prior broadcasts).
  useEffect(() => window.omiBar.requestChatState(), [])

  // --- coding agents (list view rows) -----------------------------------------
  // Track which adapter is running the current task; the terminal signal is the
  // global agentsActive dropping (no per-task "done" broadcast exists).
  useEffect(
    () =>
      window.omi.onCodingAgentEvent((e) => {
        if (e.type === 'agent_selected') setActiveAgentId(e.adapterId)
      }),
    []
  )

  // --- push-to-talk (always mounted; drives the orb + voice sends) ------------
  const ptt = usePushToTalk({
    // A blocked voice turn involves no draft — the main window speaks the line.
    onCommit: (text) => void sendFromBar(text, true),
    // Pre-capture usage veto (macOS PushToTalkManager.isBlockedByUsageLimit): refuse
    // a PTT hold BEFORE the mic opens when the user is over their monthly chat cap,
    // instead of recording + transcribing a whole turn only to refuse it at send.
    // sender.checkSync reads the already-synced local snapshot — synchronous and
    // fail-open, so the press never awaits. On a block we raise the shared popup on
    // the main window (spoken:false — the gesture veto is visual only, matching Mac).
    checkUsageLimit: () => sender.checkSync(),
    onUsageLimitBlocked: (message) => window.omiBar.notifyUsageLimit({ message, spoken: false }),
    // Barge-in: a new PTT hold cuts off Omi's still-playing spoken reply. The
    // reply plays in the MAIN window (useChat → voiceController), so hop over the
    // bar→main bridge; ChatBridgeHost calls interruptCurrentResponse there.
    onHoldStart: () => window.omiBar.interruptTts(),
    // No transcript text in the bar — the orb is the sole status indicator.
    onTranscript: () => {},
    // Fires on every completed hold capture (drives the onboarding voice step).
    onCaptureEnd: () => window.omiOverlay.notifyVoiceCaptured(),
    restoreDraft: (snapshot) => setDraft(snapshot),
    getDraft: () => draftRef.current
  })
  // Main drives PTT for the summon-hotkey hold; read the latest handlers.
  const beginHoldRef = useRef(ptt.beginHold)
  const endHoldRef = useRef(ptt.endHold)
  // eslint-disable-next-line react-hooks/refs -- latest-ref
  beginHoldRef.current = ptt.beginHold
  // eslint-disable-next-line react-hooks/refs -- latest-ref
  endHoldRef.current = ptt.endHold
  useEffect(
    () =>
      window.omiBar.onPtt((phase) => {
        // Always-on companion to main's [ptt-diag] trace: confirms the release
        // IPC actually reached the renderer. If main logs `ptt up -> renderer`
        // but this line never appears during a stuck-visualizer episode, the
        // 'up' was lost in transit; if both appear yet the orb stays in the
        // recording pose, endHold ran as a no-op (the machine was not `holding`).
        console.log(`[ptt-diag] renderer recv ${phase}`)
        if (phase === 'down') beginHoldRef.current()
        else endHoldRef.current()
      }),
    []
  )

  // Report ready ONCE the real content can render — flushes a deferred first
  // show in main (never flashes an empty frame).
  const ready = !loading && authReady
  useEffect(() => {
    if (ready) window.omiBar.ready()
  }, [ready])

  // --- main → renderer lifecycle ---------------------------------------------
  const senderRef = useRef(sender)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-registered IPC listener
  senderRef.current = sender
  useEffect(() => {
    return window.omiBar.onShow((p: BarShowPayload) => {
      setMode(p.mode)
      setSliding('in')
      // A fresh reveal drops a stale limit notice and re-reads the quota, so the
      // next send checks a current snapshot without touching the network itself.
      setLimitNotice(null)
      void senderRef.current.sync()
      // Each fresh reveal starts at the list (a summon is a pill; expanding lands
      // on the list, not a stale conversation) with no agent target carried over.
      setView('list')
      setTarget(null)
      // Signature motion: the orb materializes from nothing on every reveal.
      setGenesisNonce((n) => n + 1)
      // The bar persists across hide/show — re-pull the thread so it's current.
      window.omiBar.requestChatState()
      // Paint-ack handshake: main keeps the HWND hidden until we confirm a frame
      // with the revealed (slide-in) state has been composited — otherwise the
      // window shows the previous off-screen translateY(-110%) frame first (the
      // blank-bar paint race on first hover). A double requestAnimationFrame is
      // the Chromium-standard "the new state has been committed to a frame"
      // proxy: rAF #1 runs after the React commit but before that paint, rAF #2
      // runs after it, so by here the revealed frame is on screen.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => window.omiBar.showAck(p.token))
      })
    })
  }, [])
  useEffect(() => window.omiBar.onMode((m) => setMode(m)), [])
  useEffect(
    () =>
      window.omiBar.onWillHide(() => {
        setSliding('out')
        setView('list')
        window.setTimeout(() => window.omiBar.requestHide(), 200)
      }),
    []
  )

  // --- surface hit-testing (interactive islands) ------------------------------
  const onSurfaceEnter = useCallback((): void => window.omiBar.setInteractive(true), [])
  const onSurfaceLeave = useCallback((): void => window.omiBar.setInteractive(false), [])

  // --- Esc (only meaningful while expanded + focused) -------------------------
  // Recording/finalizing → abort the capture; in the conversation → back to the
  // list; on the list → close the bar. Window-level so it fires regardless of
  // which control has focus. Refs keep the once-registered listener current.
  const escStateRef = useRef({ view, recording: ptt.recording, transcribing: ptt.transcribing })
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-registered listener
  escStateRef.current = { view, recording: ptt.recording, transcribing: ptt.transcribing }
  const cancelPttRef = useRef(ptt.cancel)
  // eslint-disable-next-line react-hooks/refs -- latest-ref
  cancelPttRef.current = ptt.cancel
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape') return
      const s = escStateRef.current
      e.preventDefault()
      if (s.recording || s.transcribing) cancelPttRef.current()
      else if (s.view === 'conversation') setView('list')
      else window.omiOverlay.hide()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // --- pill retract hold ------------------------------------------------------
  // A summoned pill must NOT retract while a PTT hold / streaming reply / spoken
  // answer is in flight (the cursor is legitimately away the whole time). Hold it
  // open via main's watchdog suppression, then release after a short grace once
  // everything settles so the normal cursor retract can reclaim it.
  const busy = isBarBusy({
    recording: ptt.recording,
    transcribing: ptt.transcribing,
    status: chat.status
  })
  const retractTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (retractTimer.current) {
      clearTimeout(retractTimer.current)
      retractTimer.current = null
    }
    if (busy) {
      window.omiBar.keepAlive(true)
    } else {
      retractTimer.current = setTimeout(() => window.omiBar.keepAlive(false), RETRACT_GRACE_MS)
    }
    return () => {
      if (retractTimer.current) {
        clearTimeout(retractTimer.current)
        retractTimer.current = null
      }
    }
  }, [busy])

  // --- morph measurements ------------------------------------------------------
  const expanded = mode === 'expanded'
  useLayoutEffect(() => {
    const el = panelInnerRef.current
    if (!el) return
    // Cap the surface at the window height so a tall reply can't be clipped by
    // the OS edge (C4) — the message list scrolls internally instead.
    const report = (): void =>
      setPanelHeight(Math.min(window.innerHeight - 2, Math.max(96, el.offsetHeight)))
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ready, view, expanded])

  // Bound for the internally-scrolling message list (pre-zoom units), derived
  // from the window height so orb header + input + list always fit (C4).
  const maxListHeight = Math.max(160, Math.round((window.innerHeight - 150) / PANEL_ZOOM))

  // --- orb state (the sole status indicator) ----------------------------------
  // `user` (from useAuth) is the single auth source — fake-aware for the E2E and
  // equivalent to a live session in prod (both read the same auth).
  const continuousListening = continuous && !!user
  const agentsActive = chat.agentsActive ?? false
  const orb = deriveOrbState({
    recording: ptt.recording,
    transcribing: ptt.transcribing,
    status: chat.status,
    continuousListening,
    agentsActive
  })
  const orbState = orb.state
  // Pill wordmark → "Listening" whenever the user's voice is being captured
  // (PTT hold or always-on), else "Omi". Activity-keyed, not orb-pose-keyed: a
  // PTT hold derives as the 'speaking' pose but is still Omi listening to you.
  const pillText = pillLabel({ recording: ptt.recording, continuousListening })
  const amplitudeSource: (() => WaveformSource | null) | null = orb.withAmplitude
    ? () => ptt.analyserRef.current
    : null

  // Connected coding agents to list under "Omi Chat" (at most one "Working…").
  const agentRows = deriveAgentRows(agents, activeAgentId, agentsActive)

  // Open the inline conversation for a clicked row. `null` = the Omi Chat thread;
  // an agent row titles the header with its name and seeds the delegation phrasing
  // detectAgentTask matches, so the user's next words are handed to that agent
  // (they can clear it for a normal Omi turn). Returning to Omi drops a stale seed
  // but never a message the user actually typed (nextConversationDraft).
  const openConversation = (next: BarAgentRow | null): void => {
    setDraft((current) => nextConversationDraft({ target: next, previous: target, current }))
    setTarget(next)
    setView('conversation')
  }

  const surfaceStyle = expanded
    ? { width: PANEL_WIDTH, height: panelHeight }
    : { width: PILL.width, height: PILL.height }

  return (
    <div className="bar-root">
      <div className={`bar-slide ${sliding === 'in' ? 'bar-slide-in' : 'bar-slide-out'}`}>
        <div
          className={`bar-surface ${expanded ? 'bar-surface-expanded' : ''}`}
          style={surfaceStyle}
          onMouseEnter={onSurfaceEnter}
          onMouseLeave={onSurfaceLeave}
        >
          {/* Collapsed pill — orb + wordmark. Click to expand. Minimal by design:
              the orb is the status indicator (no transcript, no waveform). */}
          <div
            className={`bar-content ${!expanded ? 'bar-content-active' : ''}`}
            role="button"
            aria-label="Open Omi"
            tabIndex={-1}
            onClick={() => window.omiBar.expand()}
          >
            <div className="bar-pill">
              {/* Slot reserving the pill orb's footprint; the real orb is the ONE
                  persistent mount below, overlaid here so the label stays put. */}
              <div className="h-[26px] w-[26px] shrink-0" aria-hidden />
              <span className="bar-pill-label">{pillText}</span>
            </div>
          </div>

          {/* Expanded surface: orb header + chat list / inline conversation.
              Always mounted so it's ready to cross-dissolve on expand. */}
          <div className={`bar-content ${expanded ? 'bar-content-active' : ''}`}>
            <div ref={panelInnerRef}>
              {/* pt-3: reserve the orb header's height (the real orb is the ONE
                  persistent mount below, overlaid over this slot). */}
              <div className="relative flex items-center justify-center pt-3">
                <div className="h-[34px] w-[34px]" aria-hidden />
              </div>
              <div className="bar-zoom">
                {!ready ? (
                  <div className="px-4 pb-4 pt-2 text-sm text-neutral-400">Loading…</div>
                ) : !user ? (
                  <SignedOutContent />
                ) : (
                  <BarChatSurface
                    chat={chat}
                    agents={agentRows}
                    view={view}
                    conversationTitle={target ? target.displayName : 'Omi Chat'}
                    onOpenConversation={openConversation}
                    onBack={() => setView('list')}
                    onClose={() => window.omiOverlay.hide()}
                    draft={draft}
                    setDraft={setDraft}
                    onSubmit={(text) => sendFromBar(text, typedVoice)}
                    limitNotice={limitNotice}
                    pttKeyDown={ptt.onKeyDown}
                    pttKeyUp={ptt.onKeyUp}
                    recording={ptt.recording}
                    transcribing={ptt.transcribing}
                    maxListHeight={maxListHeight}
                  />
                )}
              </div>
            </div>
          </div>

          {/* THE orb — one persistent mount, hoisted above both cross-dissolving
              content layers and the box morph. It never remounts, fades, or
              changes size/preset (which rebuild the WebGL animator = a blink); it
              glides between its pill seat and panel-header seat via a transform-
              only FLIP (see .bar-orb / .bar-orb-wrap). This is why the logo no
              longer flashes on expand/collapse. */}
          <div className="bar-orb" aria-hidden>
            <div className="bar-orb-wrap">
              <Orb
                size={34}
                state={orbState}
                amplitudeSource={amplitudeSource}
                genesisNonce={genesisNonce}
                visible={mode !== null}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
