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
import { chunkTts } from './ttsChunker'
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

// ── Chunked bar-TTS pipeline state ────────────────────────────────────────────
// A non-realtime spoken reply is split into chunks (small first, larger after)
// and synthesized+played pipelined so time-to-first-audio ≈ one small chunk.
// `ttsGeneration` invalidates every in-flight synth/playback/filler closure the
// instant a new reply supersedes it OR a PTT barge-in interrupts (macOS
// FloatingBarVoicePlaybackService.playbackGeneration). `currentTtsAbort` aborts
// the in-flight chunk fetch so an interrupt resolves speakText promptly — which
// clears useChat.speaking → the bar orb's speaking glow.
let ttsGeneration = 0
let currentTtsAbort: AbortController | null = null
// The filler phrase (system voice) covering first-chunk synth latency; its own
// cancel handle, independent of stopCurrentTts, so it can never clobber a real
// chunk's playback teardown.
let stopCurrentFiller: (() => void) | null = null
// Ported from macOS FloatingBarVoicePlaybackService.fillerPhrases. Exported for
// the pipeline unit test.
export const FILLER_PHRASES = [
  'Let me check.',
  'One moment.',
  'Looking into it.',
  'Let me see.',
  'Checking now.',
  'Hold on.',
  'One sec.',
  'Working on it.'
]

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
  // playing on speakers would leak Omi's voice into transcription. Also aborts a
  // chunk fetch, cancels the filler, and bumps the generation so the pipeline bails.
  resetTtsPipeline()
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
// Exported for unit-testing the hang watchdog; not part of the public surface.
export async function playSystemVoice(text: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const u = new SpeechSynthesisUtterance(text)
    let settled = false
    let resumePump: ReturnType<typeof setInterval> | null = null
    let watchdog: ReturnType<typeof setTimeout> | null = null
    const cleanup = (): void => {
      if (resumePump !== null) {
        clearInterval(resumePump)
        resumePump = null
      }
      if (watchdog !== null) {
        clearTimeout(watchdog)
        watchdog = null
      }
    }
    // Settle exactly once, tearing down the pump + watchdog first.
    const done = (fn: () => void): void => {
      if (settled) return
      settled = true
      cleanup()
      fn()
    }
    // Chromium silently stalls SpeechSynthesis on long utterances (~15s) and
    // then never fires `onend` unless `resume()` is pumped — which would hang
    // this promise, wedge the echo gate, and (via useChat.speaking) freeze the
    // bar orb + keepAlive until an app restart. Pump resume() to prevent the
    // stall…
    resumePump = setInterval(() => {
      try {
        window.speechSynthesis.resume()
      } catch {
        /* ignore */
      }
    }, 10000)
    // …and a generous max-duration backstop so even if it still never ends, the
    // caller's gate/speaking state can't wedge (~10 chars/s, floor 8s, cap 120s).
    const maxMs = Math.min(120000, Math.max(8000, text.length * 100))
    watchdog = setTimeout(() => {
      try {
        window.speechSynthesis.cancel()
      } catch {
        /* ignore */
      }
      done(resolve)
    }, maxMs)
    u.onend = () => done(resolve)
    u.onerror = (e) =>
      e.error === 'interrupted' || e.error === 'canceled'
        ? done(resolve)
        : done(() => reject(new Error(`system voice failed: ${e.error}`)))
    stopCurrentTts = () => {
      try {
        window.speechSynthesis.cancel()
      } catch {
        /* ignore */
      }
      done(resolve)
    }
    window.speechSynthesis.speak(u)
  }).finally(() => {
    stopCurrentTts = null
  })
}

let ttsSeq = 0

/** Play a filler phrase (via the system voice) while the FIRST chunk is still
 *  synthesizing, so a voice reply isn't preceded by dead air. It is cancelled the
 *  instant the first real chunk's audio is ready (see runChunkedTts) so it can
 *  only ever fill the pre-first-chunk silence and never overlaps real audio. Its
 *  own cancel handle keeps it independent of a real chunk's stopCurrentTts. */
function startFiller(): void {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  const phrase = FILLER_PHRASES[Math.floor(Math.random() * FILLER_PHRASES.length)]
  try {
    const u = new SpeechSynthesisUtterance(phrase)
    stopCurrentFiller = () => {
      stopCurrentFiller = null
      try {
        window.speechSynthesis.cancel()
      } catch {
        /* ignore */
      }
    }
    window.speechSynthesis.speak(u)
    record('tts-filler', phrase)
  } catch {
    stopCurrentFiller = null
  }
}

function cancelFiller(): void {
  const stop = stopCurrentFiller
  stopCurrentFiller = null
  stop?.()
}

/** Invalidate every in-flight synth/playback/filler closure: bump the
 *  generation, abort the in-flight chunk fetch, cancel the filler, and stop the
 *  current audio element / system-voice utterance. Shared by a superseding new
 *  reply, a PTT barge-in (interruptCurrentResponse), and session teardown. */
function resetTtsPipeline(): void {
  ttsGeneration++
  currentTtsAbort?.abort()
  currentTtsAbort = null
  cancelFiller()
  stopCurrentTts?.()
}

/**
 * PTT barge-in: stop the current spoken reply immediately — stop playback,
 * cancel any in-flight synth + filler, reset the pipeline. Wired (over IPC) to
 * the start of every new PTT hold (macOS PushToTalkManager.startListening →
 * FloatingBarVoicePlaybackService.interruptCurrentResponse). Aborting the
 * in-flight synth resolves the pending speakText promise promptly, which clears
 * useChat.speaking → the bar orb's speaking glow. Safe no-op when nothing plays.
 */
export function interruptCurrentResponse(): void {
  record('tts-interrupt')
  resetTtsPipeline()
}

type ChunkAudio =
  | { kind: 'blob'; blob: Blob; text: string }
  | { kind: 'fallback'; text: string }
  | { kind: 'aborted' }

/** Synthesize one chunk, mapping a provider failure to a system-voice fallback
 *  (with the shared fallback telemetry). A generation bump / abort means an
 *  interrupt superseded this synth — NOT a provider failure, so no fallback and
 *  no telemetry. */
async function synthChunk(
  text: string,
  voiceId: string,
  gen: number,
  signal: AbortSignal
): Promise<ChunkAudio> {
  try {
    const blob = await synthesizeTts(text, voiceId, signal)
    return { kind: 'blob', blob, text }
  } catch (e) {
    if (gen !== ttsGeneration || signal.aborted) return { kind: 'aborted' }
    record('tts-fallback', (e as Error)?.message)
    trackEvent('fallback_triggered', {
      component: 'voice_tts',
      from: 'openai_tts',
      to: 'system_voice',
      reason: 'provider_unavailable',
      outcome: 'degraded'
    })
    return { kind: 'fallback', text }
  }
}

async function playChunkAudio(res: ChunkAudio, gen: number): Promise<void> {
  if (gen !== ttsGeneration || res.kind === 'aborted') return
  if (res.kind === 'blob') {
    try {
      await playTtsBlob(res.blob)
      return
    } catch {
      if (gen !== ttsGeneration) return
      // Synthesized audio that won't play (bad blob / device gone) — speak this
      // chunk with the system voice rather than dropping it (macOS parity), and
      // record the fail-open per the fallback contract.
      record('tts-fallback', 'playback')
      trackEvent('fallback_triggered', {
        component: 'voice_tts',
        from: 'openai_tts',
        to: 'system_voice',
        reason: 'provider_unavailable',
        outcome: 'degraded'
      })
    }
  }
  if (gen !== ttsGeneration) return
  await playSystemVoice(res.text)
}

/** Pipeline: begin synthesizing chunk N+1 while chunk N plays, so a long reply's
 *  time-to-first-audio is one small chunk, not the whole reply. */
async function runChunkedTts(
  chunks: string[],
  voiceId: string,
  gen: number,
  signal: AbortSignal
): Promise<void> {
  // Cover the first-chunk synth latency with a filler ONLY for multi-chunk
  // replies — a short single-chunk reply keeps its original (filler-free) shape.
  const useFiller = chunks.length > 1
  if (useFiller) startFiller()
  let nextSynth = synthChunk(chunks[0], voiceId, gen, signal)
  for (let i = 0; i < chunks.length; i++) {
    const res = await nextSynth
    if (gen !== ttsGeneration) return
    // Kick the NEXT chunk's synthesis before playing THIS one (pipelining).
    if (i + 1 < chunks.length) nextSynth = synthChunk(chunks[i + 1], voiceId, gen, signal)
    // First real audio preempts the filler — cancel it before any real audio.
    if (i === 0 && useFiller) cancelFiller()
    if (res.kind === 'aborted') return
    await playChunkAudio(res, gen)
    if (gen !== ttsGeneration) return
  }
}

/**
 * Speak a non-realtime reply through the SAME gated output path: gate on while
 * audible, source text injected into the record, gate releases after playback
 * drains. Works with or without a live session. The reply is split into chunks
 * (small first for a fast start, larger after) and synthesized+played pipelined;
 * each chunk prefers backend TTS (/v1/tts/synthesize) and falls back to the
 * system voice — the same contract as the macOS client — so a spoken reply still
 * happens. A short single-chunk reply keeps the original one-synth-then-play
 * shape (no filler).
 */
export async function speakText(text: string, voiceId: string = DEFAULT_TTS_VOICE): Promise<void> {
  const chunks = chunkTts(text)
  if (chunks.length === 0) return

  // A fresh reply supersedes anything still playing/synthesizing and takes a new
  // generation + abort handle (so a barge-in can invalidate exactly this run).
  resetTtsPipeline()
  const gen = ttsGeneration
  const abort = new AbortController()
  currentTtsAbort = abort

  record('tts-start', text.slice(0, 80))
  // Inject the FULL reply text into the capture record once (echo-gate contract),
  // regardless of how many chunks it plays as.
  window.omi?.captureCommand({
    type: 'assistant-utterance',
    utteranceId: `tts-${ttsSeq++}`,
    text
  })
  watchdogReported = false
  gate.playbackStarted(Date.now())
  syncGate()
  try {
    await runChunkedTts(chunks, voiceId, gen, abort.signal)
  } finally {
    if (currentTtsAbort === abort) currentTtsAbort = null
    record('tts-end')
    gate.playbackDrained(Date.now())
    syncGate()
  }
}
