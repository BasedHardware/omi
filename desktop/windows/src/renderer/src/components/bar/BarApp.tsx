// The top-edge bar renderer (#/bar) — the shell inside the fixed transparent
// window. Owns the reveal motion (slide-in from the edge), the pill ⇄ panel
// morph (ONE surface element interpolating size + radius — never a crossfade
// of two components), the interactive-island hit-testing handshake, the
// edge-hover grace period, and the orb wired to real app state (PTT capturing
// → speaking with live amplitude; reply streaming → thinking; continuous
// listening → listening; else idle).
//
// The expanded content is the ask/chat panel migrated from the old overlay
// (AskPanel) — kept mounted across modes so chat history survives.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useAuth } from '../../hooks/useAuth'
import { auth } from '../../lib/firebase'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import { Orb } from '../orb/Orb'
import { AskPanel, type AskPanelActivity } from './AskPanel'
import type { BarMode, BarShowPayload, WaveformSource } from '../../../../shared/types'
import type { OrbState } from '../../orb/choreography'
import './bar.css'

const PILL = { width: 148, height: 36 }
const PANEL_WIDTH = 336
const HOVER_GRACE_MS = 600

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
  const [activity, setActivity] = useState<AskPanelActivity>({
    recording: false,
    transcribing: false,
    sending: false,
    getAnalyser: () => null
  })
  const [continuous, setContinuous] = useState(() => !!getPreferences().continuousRecording)
  const [signedIn, setSignedIn] = useState(() => !!auth.currentUser)
  const pttRef = useRef<{ beginHold: () => void; endHold: () => void } | null>(null)
  const graceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const modeRef = useRef<BarMode | null>(null)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for IPC listeners
  modeRef.current = mode
  const panelInnerRef = useRef<HTMLDivElement>(null)
  const [panelHeight, setPanelHeight] = useState(120)

  // Transparent page background (the window has no material).
  useEffect(() => {
    document.body.classList.add('bar-body')
    return () => document.body.classList.remove('bar-body')
  }, [])

  useEffect(() => onPreferencesChange((p) => setContinuous(!!p.continuousRecording)), [])
  useEffect(() => {
    let active = true
    void auth.authStateReady().then(() => {
      if (active) setAuthReady(true)
    })
    const unsub = auth.onAuthStateChanged((u) => setSignedIn(!!u))
    return () => {
      active = false
      unsub()
    }
  }, [])

  // Report ready ONCE the real content can render — flushes a deferred first
  // show in main (never flashes an empty frame).
  const ready = !loading && authReady
  useEffect(() => {
    if (ready) window.omiBar.ready()
  }, [ready])

  // --- main → renderer lifecycle ---------------------------------------------
  useEffect(() => {
    return window.omiBar.onShow((p: BarShowPayload) => {
      setMode(p.mode)
      setSliding('in')
      // Signature motion: the orb materializes from nothing on every reveal.
      setGenesisNonce((n) => n + 1)
    })
  }, [])
  useEffect(() => window.omiBar.onMode((m) => setMode(m)), [])
  useEffect(
    () =>
      window.omiBar.onWillHide(() => {
        setSliding('out')
        window.setTimeout(() => window.omiBar.requestHide(), 200)
      }),
    []
  )
  // Summon-hotkey physical hold → the existing PTT machine (its own 350ms
  // threshold decides tap vs hold, so a quick tap records nothing).
  useEffect(
    () =>
      window.omiBar.onPtt((phase) => {
        if (phase === 'down') pttRef.current?.beginHold()
        else pttRef.current?.endHold()
      }),
    []
  )

  // --- hover grace (edge-hover reveals only) ----------------------------------
  const clearGrace = useCallback((): void => {
    if (graceTimer.current) {
      clearTimeout(graceTimer.current)
      graceTimer.current = null
    }
  }, [])
  const onSurfaceEnter = useCallback((): void => {
    clearGrace()
    window.omiBar.setInteractive(true)
  }, [clearGrace])
  const onSurfaceLeave = useCallback((): void => {
    window.omiBar.setInteractive(false)
    // Cursor left the surface: a strip-revealed peek slides away after a grace
    // period. Expanded/ptt stay (they're dismissed by hotkey/✕).
    if (modeRef.current === 'peek') {
      clearGrace()
      graceTimer.current = setTimeout(() => {
        if (modeRef.current === 'peek') {
          setSliding('out')
          window.setTimeout(() => window.omiBar.requestHide(), 200)
        }
      }, HOVER_GRACE_MS)
    }
  }, [clearGrace])
  useEffect(() => clearGrace, [clearGrace])

  // --- morph measurements ------------------------------------------------------
  const expanded = mode === 'expanded' || mode === 'ptt'
  useLayoutEffect(() => {
    const el = panelInnerRef.current
    if (!el) return
    const report = (): void => setPanelHeight(Math.max(96, el.offsetHeight))
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ready])

  // --- orb state ----------------------------------------------------------------
  let orbState: OrbState = 'idle'
  let amplitudeSource: (() => WaveformSource | null) | null = null
  if (activity.recording) {
    orbState = 'speaking'
    amplitudeSource = activity.getAnalyser
  } else if (activity.sending || activity.transcribing) {
    orbState = 'thinking'
  } else if (continuous && signedIn) {
    orbState = 'listening'
  }

  const surfaceStyle = expanded
    ? { width: PANEL_WIDTH, height: panelHeight }
    : { width: PILL.width, height: PILL.height }

  const stateLabel = activity.recording
    ? 'listening'
    : activity.sending || activity.transcribing
      ? 'thinking'
      : continuous && signedIn
        ? 'listening'
        : 'idle'

  return (
    <div className="bar-root">
      <div className={`bar-slide ${sliding === 'in' ? 'bar-slide-in' : 'bar-slide-out'}`}>
        <div
          className={`bar-surface ${expanded ? 'bar-surface-expanded' : ''}`}
          style={surfaceStyle}
          onMouseEnter={onSurfaceEnter}
          onMouseLeave={onSurfaceLeave}
        >
          {/* Collapsed pill — the orb + a whisper of state. Click to expand. */}
          <div
            className={`bar-content ${!expanded ? 'bar-content-active' : ''}`}
            role="button"
            aria-label="Open Omi"
            tabIndex={-1}
            onClick={() => window.omiBar.expand()}
          >
            <div className="bar-pill">
              <Orb
                size={26}
                state={orbState}
                amplitudeSource={amplitudeSource}
                genesisNonce={genesisNonce}
                visible={mode !== null}
              />
              <span className="bar-pill-label">Omi</span>
              <span className="bar-pill-state">{stateLabel}</span>
            </div>
          </div>

          {/* Expanded ask surface (migrated overlay panel). Always mounted so
              chat history survives; the empty state always renders the input
              row + orb — never a blank panel (bug backlog: idle blank card). */}
          <div className={`bar-content ${expanded ? 'bar-content-active' : ''}`}>
            <div ref={panelInnerRef}>
              <div className="relative flex items-center justify-center pt-2">
                <Orb
                  size={34}
                  state={orbState}
                  amplitudeSource={amplitudeSource}
                  genesisNonce={genesisNonce}
                  visible={mode !== null && expanded}
                />
              </div>
              <div className="bar-zoom">
                {!ready ? (
                  <div className="px-4 pb-4 pt-2 text-sm text-neutral-400">Loading…</div>
                ) : !user ? (
                  <SignedOutContent />
                ) : (
                  <AskPanel
                    onRegisterPtt={(h) => {
                      pttRef.current = h
                    }}
                    onActivity={setActivity}
                    onClose={() => window.omiOverlay.hide()}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
