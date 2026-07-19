import { useEffect, useRef, useState } from 'react'
import { useAppState } from '../../state/appState'
import { useAuth } from '../../hooks/useAuth'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import { useHubWarmLifecycle } from '../../hooks/useHubWarmLifecycle'
import { interruptCurrentResponse } from '../../lib/voice/voiceController'
import { startPttCapture } from '../../lib/ptt/capture'
import { batchTranscribe } from '../../lib/ptt/transport'
import { muteSystemAudioForHubCapture } from '../../lib/ptt/systemAudioMute'
import { HubController } from '../../lib/voice/hub/hubController'
import { VoiceHubTurnDriver } from '../../lib/voice/turn/voiceHubTurnDriver'
import { subscribePlaybackLevel } from '../../lib/voice/playbackLevelBus'

// The main-window mount for the warm-hub PTT driver (A5 PR-6b, Option A / D1).
//
// The coordinator + host + hub controller + output coordinator all run HERE
// because `pcmPlayer` and `voiceController` are main-resident — so hub spoken
// audio plays locally with zero audio IPC. This host wires the driver's injected
// seams to the real subsystems and subscribes to the three bar→main control
// channels (begin / end / cancel).
//
// The kill-switch is structural: the bar sends `voiceHubBegin` ONLY when
// `pttHubEnabled` is on, so with the flag off this host constructs its (pure,
// unconnected) objects and registers three listeners that NEVER fire — no
// capture, no hub warm, no projection. The shipped local PTT cascade is untouched.
export function VoiceHubDriverHost(): null {
  const { chat } = useAppState()
  const { user, loading } = useAuth()
  // Eager-warm gate (the pttHubEnabled opt-out contract). Reactive so a runtime
  // toggle warms/tears down with no restart.
  const [hubEnabled, setHubEnabled] = useState(() => getPreferences().pttHubEnabled === true)
  useEffect(() => onPreferencesChange((p) => setHubEnabled(p.pttHubEnabled === true)), [])

  // Latest-ref so the once-constructed driver always drives the freshest send.
  const sendRef = useRef(chat.send)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-built driver
  sendRef.current = chat.send
  // Latest-ref for the hub-turn recorder (append, no re-answer) — reads the freshest
  // history so a recorded turn lands after everything sent before it.
  const recordVoiceTurnRef = useRef(chat.recordVoiceTurn)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-built driver
  recordVoiceTurnRef.current = chat.recordVoiceTurn
  // Latest-ref for the continuity-seed reader (the same chat thread's kernel tail).
  const getSeedRef = useRef(chat.getVoiceSeedContext)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-built driver
  getSeedRef.current = chat.getVoiceSeedContext

  // Built once. Every collaborator points at the real main-resident subsystem:
  //   * hub session (playback via its own pcmPlayer, D3) — HubController.
  //   * barge-in — voiceController.interruptCurrentResponse (the existing channel).
  //   * capture — startPttCapture issued FROM MAIN, so owned PCM routes here.
  //   * cascade STT (omniSTT route + warm-wait fallback) — transport.batchTranscribe.
  //   * final transcript — the ONE chat engine's send (fromVoice ⇒ spoken reply).
  //   * orb projection — publishVoiceHubState (main → bar).
  const [driver] = useState(
    // eslint-disable-next-line react-hooks/refs -- latest-ref (sendRef) is read at turn-commit time inside the once-built driver, never during render
    () =>
      new VoiceHubTurnDriver({
        createHub: (events) =>
          new HubController({
            events,
            // Seed a realtime session with the shared thread's recent turns (PR-B).
            // Reads the SAME conversation the typed tail reads, via the chat hook so
            // the chatId stays encapsulated.
            fetchSeed: () => getSeedRef.current(),
            // Advertise the host-built voice tool catalog (PR-C). Role is host-derived
            // main-side (never model/renderer-claimed); empty until signed in.
            fetchTools: () => window.omi?.voiceHubToolCatalog?.() ?? Promise.resolve([])
          }),
        interruptPlayback: (leaseID) => interruptCurrentResponse(leaseID),
        publishState: (state) => window.omi?.publishVoiceHubState?.(state),
        startCapture: (opts) => startPttCapture(opts),
        transcribe: (pcm) => batchTranscribe(pcm, new AbortController().signal),
        // CASCADE route: re-answer via the chat engine (fromVoice ⇒ spoken reply).
        // Thread the per-press turnId so the kernel user-turn record shares the key a
        // hub-native record would use (INV-CHAT-1 double-record belt-and-suspenders).
        onFinalText: (text, turnId) =>
          void sendRef.current(text, { fromVoice: true, idempotencyKey: turnId }),
        // A completed HUB turn: APPEND its text to the ONE chat engine (INV-CHAT-1),
        // no LLM/TTS re-run (the hub already spoke it). Threads `interrupted` (a
        // barge-in still records a partial reply) and the per-press turnId (the
        // kernel dedupe key).
        onRecordTurn: (userText, assistantText, interrupted, turnId) =>
          recordVoiceTurnRef.current(userText, assistantText, interrupted, turnId),
        // Dispatch a spoken tool request IN-PROCESS via the shared host executor
        // registry (PR-C). Authority is host-derived main-side; the model supplies
        // only the name + arguments. Never throws — main returns "Error: …" strings.
        executeTool: (name, argumentsJSON) =>
          window.omi?.voiceToolExecute?.({ name, argumentsJSON }) ??
          Promise.resolve('Error: tools are not available'),
        muteForCapture: muteSystemAudioForHubCapture
      })
  )

  // Forward the reply's PLAYBACK loudness to the bar. The PCM player (main-window
  // resident, D3) posts the played audio's linear peak on the renderer-local bus;
  // relaying it main → bar lets the orb's speaking pose move with the reply's
  // real speech dynamics instead of sitting frozen. Tiny numeric frames at ~31Hz
  // only while audio actually plays — never per-frame audio over IPC.
  useEffect(
    () => subscribePlaybackLevel((level) => window.omi?.publishVoicePlaybackLevel?.(level)),
    []
  )

  useEffect(() => {
    const un1 = window.omi?.onVoiceHubBegin?.((p) => driver.begin(p))
    const un2 = window.omi?.onVoiceHubEnd?.(() => driver.end())
    const un3 = window.omi?.onVoiceHubCancel?.(() => driver.cancel())
    // A7c wake: the machine resumed/unlocked — a socket warmed before suspend is likely
    // a zombie, so refresh it now (idle) rather than let the next press land on it dead.
    const un4 = window.omi?.onVoiceHubWake?.(() => driver.requestSessionRefresh('system_wake'))
    return () => {
      un1?.()
      un2?.()
      un3?.()
      un4?.()
    }
  }, [driver])

  // Eagerly warm the hub for a signed-in user with the flag on. This is what makes
  // hub.isAvailable() true — without it selectPttRoute always picks the cascade and
  // the warm hub never engages. Tears down on toggle-off / sign-out.
  useHubWarmLifecycle(driver, { ready: !loading, signedIn: !!user, hubEnabled })

  // Refresh the hub's continuity seed whenever the shared thread grows — a typed
  // turn (or the initial history load) means the warm session is now stale, so the
  // NEXT voice turn's realtime session should carry it. The controller only
  // reconnects when the fresh seed holds a turn it hasn't seen (a self-produced
  // voice turn is already marked known, so it doesn't thrash), and never mid-turn.
  // Doing it on thread-change (not per-press) keeps the mic-start path latency-free.
  const threadLen = chat.history.length
  useEffect(() => {
    driver.refreshSeedContext()
  }, [driver, threadLen])

  return null
}
