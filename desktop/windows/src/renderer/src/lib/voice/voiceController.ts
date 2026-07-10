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
let lastSentGate = false
let sinkId = '' // '' = system default

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

function syncGate(): void {
  const now = Date.now()
  const active = gate.isActive(now)
  if (active !== lastSentGate) {
    lastSentGate = active
    window.omi?.captureCommand({ type: 'assistant-speaking', active })
    record(active ? 'gate-on' : 'gate-off')
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
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    const headset = isHeadsetOutput(devices, sinkId)
    gate.setHeadset(headset)
    syncGate()
    return headset
  } catch {
    gate.setHeadset(false) // fail closed: assume speakers, keep the gate hard
    return false
  }
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
      record('speaking-start')
      gate.playbackStarted()
      syncGate()
    },
    onSpeakingEnd: () => {
      record('speaking-end')
      gate.playbackDrained(Date.now())
      syncGate()
    },
    onUtterance: (utteranceId, text) => {
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
  navigator.mediaDevices?.removeEventListener?.('devicechange', onDeviceChange)
  // Release the gate NOW — with the session gone there is no more assistant
  // audio; a stuck gate would silently deafen continuous transcription.
  gate.interrupted(0) // any pending tail collapses…
  gate.setHeadset(false)
  if (gateTimer) {
    clearTimeout(gateTimer)
    gateTimer = null
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
  try {
    handle =
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
    // Stopped while the provider handshake was in flight.
    handle?.stop()
    handle = null
    return
  }
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

/**
 * Speak a non-realtime reply via backend TTS, through the SAME gated output
 * path: gate on while audible, source text injected into the record, gate
 * releases after the element finishes. Works with or without a live session.
 */
let ttsSeq = 0
export async function speakText(text: string, voiceId: string = DEFAULT_TTS_VOICE): Promise<void> {
  const blob = await synthesizeTts(text, voiceId)
  const url = URL.createObjectURL(blob)
  const el = new Audio()
  el.src = url
  if (sinkId) {
    await el.setSinkId(sinkId).catch(() => {
      /* unknown device — default */
    })
  }
  record('tts-start', text.slice(0, 80))
  window.omi?.captureCommand({
    type: 'assistant-utterance',
    utteranceId: `tts-${ttsSeq++}`,
    text
  })
  gate.playbackStarted()
  syncGate()
  try {
    await el.play()
    await new Promise<void>((resolve) => {
      el.onended = () => resolve()
      el.onerror = () => resolve()
    })
  } finally {
    record('tts-end')
    gate.playbackDrained(Date.now())
    syncGate()
    URL.revokeObjectURL(url)
  }
}
