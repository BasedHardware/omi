// The realtime-voice orchestrator (Phase 6) — a module singleton the UI surface
// (and later the Phase 4 bar) drives. Owns:
//  - the pure session machine (sessionMachine.ts) + subscriber fanout
//  - token mint with provider fallback (openai → gemini and vice versa)
//  - the echo-gate DRIVER: pure EchoGate decisions + the one timer + the
//    'assistant-speaking' capture commands (the capture window enforces)
//  - injected transcripts ('assistant-utterance') from provider source text
//  - usage reporting to /v2/realtime/usage (best-effort)
//  - output-device routing (setSinkId on both lanes) + headset detection
//  - TTS playback for non-realtime spoken replies, through the same gated path

import { trackEvent } from '../analytics'
import {
  initialVoiceState,
  transition,
  type VoiceProvider,
  type VoiceSessionState,
  type VoiceSessionEvent
} from './sessionMachine'
import { EchoGate, isHeadsetOutput } from './echoGate'
import { GATE_REASSERT_MS } from '../../capture/assistantGate'
import { mintRealtimeToken, MintError } from './tokenMint'
import { reportRealtimeUsage } from './usageReport'
import { startOpenAiSession } from './openaiSession'
import { startGeminiSession } from './geminiSession'
import { synthesizeTts, DEFAULT_TTS_VOICE } from './tts'
import type { ProviderSessionCallbacks, ProviderSessionHandle } from './providerSession'

type Listener = (state: VoiceSessionState) => void

/** Timestamped event trail for the live loop-check harness (capped ring). */
export type VoiceEventRecord = { at: number; type: string; detail?: string }

let state: VoiceSessionState = initialVoiceState
const listeners = new Set<Listener>()
let handle: ProviderSessionHandle | null = null
let startSeq = 0 // invalidates in-flight async starts after stop()

const gate = new EchoGate()
let gateTimer: ReturnType<typeof setTimeout> | null = null
// Periodic re-assert while the gate is held: the capture side treats an ON
// older than its TTL as released (resilience against this window dying while
// Omi speaks), so a held gate must be refreshed faster than that TTL.
let gateReassertTimer: ReturnType<typeof setInterval> | null = null
let lastSentGate = false
let sinkId = '' // '' = system default
// In-flight TTS element teardown hook — stopVoiceSession must silence TTS too,
// otherwise the gate is force-released while Omi is still audible on speakers.
let stopCurrentTts: (() => void) | null = null

const events: VoiceEventRecord[] = []
function record(type: string, detail?: string): void {
  events.push({ at: Date.now(), type, detail })
  if (events.length > 200) events.splice(0, events.length - 200)
}

function dispatch(event: VoiceSessionEvent): void {
  const next = transition(state, event)
  if (next === state) return
  state = next
  for (const l of listeners) l(state)
}

// ── Echo-gate driver ──────────────────────────────────────────────────────────
// The pure EchoGate answers "paused right now?"; this driver diffs that answer,
// sends the capture command on change, and arms exactly one timer for the
// release edge (the only transition that happens without an event).

// The watchdog (EchoGate.maxHoldMs) force-releasing means a terminal
// speaking-end edge was MISSED — a correctness fail-open worth telemetry, once
// per stuck burst (silent ops is not ok; see AGENTS.md fallback rules).
let watchdogReported = false

function syncGate(): void {
  const now = Date.now()
  if (gate.watchdogExpired(now) && !watchdogReported) {
    watchdogReported = true
    record('gate-watchdog')
    trackEvent('fallback_triggered', {
      component: 'voice_echo_gate',
      from: 'gated',
      to: 'released',
      reason: 'watchdog_max_hold',
      outcome: 'degraded'
    })
  }
  const active = gate.isActive(now)
  if (active !== lastSentGate) {
    lastSentGate = active
    window.omi?.captureCommand({ type: 'assistant-speaking', active })
    record(active ? 'gate-on' : 'gate-off')
  }
  // While held, keep re-asserting so the capture side's TTL never lapses
  // mid-speech; stop as soon as the gate drops.
  if (active && gateReassertTimer === null) {
    gateReassertTimer = setInterval(() => {
      window.omi?.captureCommand({ type: 'assistant-speaking', active: true })
    }, GATE_REASSERT_MS)
  } else if (!active && gateReassertTimer !== null) {
    clearInterval(gateReassertTimer)
    gateReassertTimer = null
  }
  if (gateTimer) {
    clearTimeout(gateTimer)
    gateTimer = null
  }
  const edge = gate.nextTransitionAt(now)
  if (edge !== null) {
    gateTimer = setTimeout(syncGate, Math.max(0, edge - now) + 1)
  }
}

async function refreshHeadsetState(): Promise<boolean> {
  let headset = false
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    headset = isHeadsetOutput(devices, sinkId)
  } catch {
    headset = false // fail closed: assume speakers, keep the gate hard
  }
  gate.setHeadset(headset)
  syncGate()
  return headset
}

function onDeviceChange(): void {
  void refreshHeadsetState()
}

// ── Provider callbacks (shared by both lanes) ─────────────────────────────────

function makeCallbacks(mySeq: number): ProviderSessionCallbacks {
  return {
    onConnected: () => {
      if (mySeq !== startSeq) return
      record('connected')
      dispatch({ type: 'connected' })
    },
    onFatal: (message, retryable) => {
      if (mySeq !== startSeq) return
      record('fatal', message)
      teardown()
      dispatch({ type: 'fail', message, retryable })
    },
    onSpeakingStart: () => {
      if (mySeq !== startSeq) return // late event from a stopped session
      record('speaking-start')
      watchdogReported = false
      gate.playbackStarted(Date.now())
      syncGate()
    },
    onSpeakingEnd: () => {
      if (mySeq !== startSeq) return
      record('speaking-end')
      gate.playbackDrained(Date.now())
      syncGate()
    },
    onUtterance: (utteranceId, text) => {
      if (mySeq !== startSeq) return
      record('utterance', text)
      window.omi?.captureCommand({ type: 'assistant-utterance', utteranceId, text })
    },
    onUsage: (body) => {
      void reportRealtimeUsage(body)
    }
  }
}

function teardown(): void {
  handle?.stop()
  handle = null
  // Silence any in-flight TTS — releasing the gate while a TTS element keeps
  // playing on speakers would leak Omi's voice into transcription.
  stopCurrentTts?.()
  navigator.mediaDevices?.removeEventListener?.('devicechange', onDeviceChange)
  // Release the gate NOW — with the session gone there is no more assistant
  // audio; a stuck gate would silently deafen continuous transcription.
  gate.reset()
  if (gateTimer) {
    clearTimeout(gateTimer)
    gateTimer = null
  }
  if (gateReassertTimer) {
    clearInterval(gateReassertTimer)
    gateReassertTimer = null
  }
  if (lastSentGate) {
    lastSentGate = false
    window.omi?.captureCommand({ type: 'assistant-speaking', active: false })
    record('gate-off')
  }
}

// ── Public surface ────────────────────────────────────────────────────────────

export function getVoiceState(): VoiceSessionState {
  return state
}

export function subscribeVoiceState(fn: Listener): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function getVoiceEvents(): VoiceEventRecord[] {
  return events.slice()
}

export async function startVoiceSession(preferred: VoiceProvider = 'openai'): Promise<void> {
  if (state.status === 'connecting' || state.status === 'live') return
  const mySeq = ++startSeq
  dispatch({ type: 'start', provider: preferred })
  record('start', preferred)

  const headset = await refreshHeadsetState()

  // Mint, falling back to the other lane when THIS provider is down/unconfigured.
  let provider = preferred
  let token: string
  try {
    try {
      token = (await mintRealtimeToken(provider)).token
    } catch (e) {
      const failure = e instanceof MintError ? e.failure : null
      if (!failure?.tryOtherProvider) throw e
      const other: VoiceProvider = provider === 'openai' ? 'gemini' : 'openai'
      trackEvent('fallback_triggered', {
        component: 'realtime_mint',
        from: provider,
        to: other,
        reason: 'provider_unavailable',
        outcome: 'recovered'
      })
      provider = other
      if (mySeq === startSeq) dispatch({ type: 'provider-changed', provider })
      token = (await mintRealtimeToken(provider)).token
    }
  } catch (e) {
    if (mySeq !== startSeq) return // user stopped while minting
    const failure = e instanceof MintError ? e.failure : null
    record('mint-failed', failure?.message ?? (e as Error)?.message)
    dispatch({
      type: 'fail',
      message: failure?.message ?? `voice session failed: ${(e as Error)?.message ?? e}`,
      retryable: failure?.retryable ?? true
    })
    return
  }
  if (mySeq !== startSeq) return

  const cb = makeCallbacks(mySeq)
  // Await into a LOCAL first — publishing to the module `handle` before the
  // staleness check would let a stale start overwrite (and then stop+null) a
  // newer session's handle, orphaning its live mic/socket.
  let session: ProviderSessionHandle
  try {
    session =
      provider === 'openai'
        ? await startOpenAiSession({
            clientSecret: token,
            onSpeakers: !headset,
            sinkId: sinkId || undefined,
            cb
          })
        : await startGeminiSession({ authToken: token, sinkId: sinkId || undefined, cb })
  } catch (e) {
    if (mySeq !== startSeq) return
    dispatch({ type: 'fail', message: (e as Error)?.message ?? String(e), retryable: true })
    return
  }
  if (mySeq !== startSeq) {
    // Stopped (or superseded) while the provider handshake was in flight —
    // tear down THIS session only; never touch the module handle.
    session.stop()
    return
  }
  handle = session
  navigator.mediaDevices?.addEventListener?.('devicechange', onDeviceChange)
}

export function stopVoiceSession(): void {
  startSeq++ // invalidate any in-flight start
  record('stop')
  teardown()
  dispatch({ type: 'stop' })
}

export function setVoiceMuted(muted: boolean): void {
  handle?.setMuted(muted)
  dispatch({ type: 'set-muted', muted })
}

/** Typed user turn into the live voice conversation (model replies with voice). */
export function sendVoiceText(text: string): void {
  handle?.sendUserText(text)
  record('user-text', text.slice(0, 80))
}

/** Route Omi's voice to another output device mid-conversation. */
export async function setVoiceOutputDevice(deviceId: string): Promise<void> {
  sinkId = deviceId
  record('set-output', deviceId || 'default')
  await handle?.setOutputDevice(deviceId)
  await refreshHeadsetState()
}

/** The currently selected output device ('' = system default) — so a
 *  remounting UI surface can show the persisted routing. */
export function getVoiceOutputDevice(): string {
  return sinkId
}

/** Play a backend-TTS mp3 blob through an <audio> element on the selected
 *  sink. Resolves when playback ends (or teardown silences it). */
async function playTtsBlob(blob: Blob): Promise<void> {
  const url = URL.createObjectURL(blob)
  const el = new Audio()
  el.src = url
  if (sinkId) {
    await el.setSinkId(sinkId).catch(() => {
      /* unknown device — default */
    })
  }
  try {
    let finish: () => void = () => {}
    const done = new Promise<void>((resolve) => {
      finish = resolve
    })
    el.onended = () => finish()
    el.onerror = () => finish()
    // teardown() silences an in-flight TTS: pause the element AND resolve the
    // waiter so the caller's finally drains the gate immediately.
    stopCurrentTts = () => {
      try {
        el.pause()
      } catch {
        /* ignore */
      }
      finish()
    }
    await el.play()
    await done
  } finally {
    stopCurrentTts = null
    el.onended = null
    el.onerror = null
    el.src = ''
    URL.revokeObjectURL(url)
  }
}

/** System-voice fallback (Web Speech API → SAPI). Always plays on the system
 *  DEFAULT output (speechSynthesis has no sink routing) — fine for a fallback;
 *  the echo gate still engages around it. */
async function playSystemVoice(text: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const u = new SpeechSynthesisUtterance(text)
    u.onend = () => resolve()
    u.onerror = (e) =>
      e.error === 'interrupted' || e.error === 'canceled'
        ? resolve()
        : reject(new Error(`system voice failed: ${e.error}`))
    stopCurrentTts = () => {
      try {
        window.speechSynthesis.cancel()
      } catch {
        /* ignore */
      }
      resolve()
    }
    window.speechSynthesis.speak(u)
  }).finally(() => {
    stopCurrentTts = null
  })
}

/**
 * Speak a non-realtime reply through the SAME gated output path: gate on while
 * audible, source text injected into the record, gate releases after playback
 * drains. Works with or without a live session. Prefers backend TTS
 * (/v1/tts/synthesize); when that fails (e.g. the backend's server-key TTS is
 * unavailable) it falls back to the system voice — the same contract as the
 * macOS client — so a spoken reply still happens.
 */
let ttsSeq = 0
export async function speakText(text: string, voiceId: string = DEFAULT_TTS_VOICE): Promise<void> {
  // Resolve the audio source FIRST — if neither lane can speak, throw without
  // ever engaging the gate or injecting a line for words never said.
  let play: () => Promise<void>
  try {
    const blob = await synthesizeTts(text, voiceId)
    play = () => playTtsBlob(blob)
  } catch (e) {
    record('tts-fallback', (e as Error)?.message)
    trackEvent('fallback_triggered', {
      component: 'voice_tts',
      from: 'openai_tts',
      to: 'system_voice',
      reason: 'provider_unavailable',
      outcome: 'degraded'
    })
    play = () => playSystemVoice(text)
  }
  record('tts-start', text.slice(0, 80))
  window.omi?.captureCommand({
    type: 'assistant-utterance',
    utteranceId: `tts-${ttsSeq++}`,
    text
  })
  watchdogReported = false
  gate.playbackStarted(Date.now())
  syncGate()
  try {
    await play()
  } finally {
    record('tts-end')
    gate.playbackDrained(Date.now())
    syncGate()
  }
}
