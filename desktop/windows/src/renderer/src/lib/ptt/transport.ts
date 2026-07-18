// Push-to-talk transports.
//
// Stream lane (opportunistic): rides the existing main-process WebSocket to
// `/v2/voice-message/transcribe-stream` purely for live interim text and the
// fast-commit path. It is NEVER load-bearing: no connect await, no connect
// timeout — connection state is just an event, and any death simply means the
// batch lane does the work.
//
// Batch lane (foundation): one authed POST of the retained PCM buffer to
// `/v2/voice-message/transcribe`. This is what guarantees a hold ALWAYS
// resolves — measured baseline: ~0.5-1.2s round-trip for a few seconds of
// speech.
import axios from 'axios'
import { omiApi } from '../apiClient'
import { auth } from '../firebase'
import { getPreferences } from '../preferences'
import {
  BATCH_TIMEOUT_MS,
  BATCH_TRANSCRIBE_PATH,
  batchTranscribeParams,
  RECORDING_TOO_LONG_MESSAGE
} from './constants'
import { consumePttKeywords, pttKeywordsParam } from './vocabulary'
import type { BackendSegment } from '../../../../shared/types'

/** Fire-and-forget token warm-up for key-down: Firebase caches the result, so
 *  the awaited fetch inside startPttStream/batchTranscribe resolves from cache
 *  instead of putting a refresh round-trip on the gesture path. */
export function prefetchAuthToken(): void {
  void auth.currentUser?.getIdToken()
}

export type PttStreamCallbacks = {
  /** The socket reached OPEN. */
  onConnected: () => void
  /** A finalized transcript segment arrived (one call per non-empty segment). */
  onFinal: (text: string) => void
  /** The stream is over (error or close) — fires at most once. */
  onDead: () => void
}

export type PttStream = {
  /** Forward a capture chunk. No-op after finalize()/stop(). */
  feed: (pcm: Int16Array) => void
  /** Ask the backend to flush + endpoint promptly. Only send when connected. */
  finalize: () => void
  /** Close the session and unsubscribe. Safe to call repeatedly. */
  stop: () => void
}

let nextStreamId = 1

/** Open the opportunistic stream. Resolves once the IPC session is CREATED (the
 *  socket is still connecting — onConnected reports OPEN separately). Rejects
 *  only if there is no signed-in user. */
export async function startPttStream(cb: PttStreamCallbacks): Promise<PttStream> {
  const user = auth.currentUser
  if (!user) throw new Error('push-to-talk requires sign-in')
  const token = await user.getIdToken()
  const sessionId = `ptt-stream-${Date.now()}-${nextStreamId++}`

  let over = false
  let stopped = false
  const die = (): void => {
    if (over) return
    over = true
    cb.onDead()
  }

  const unsub = window.omi.onListenMessage((msg) => {
    if (msg.sessionId !== sessionId) return
    if (msg.kind === 'connected') {
      cb.onConnected()
    } else if (msg.kind === 'segments') {
      for (const seg of msg.segments as BackendSegment[]) {
        const text = (seg.text ?? '').trim()
        if (text) cb.onFinal(text)
      }
    } else if (msg.kind === 'closed') {
      die()
    } else if (msg.kind === 'error' && msg.fatal) {
      die()
    }
  })

  try {
    await window.omi.listenStart({
      sessionId,
      source: 'mic',
      token,
      language: getPreferences().language,
      mode: 'ptt'
    })
  } catch (e) {
    unsub()
    throw e
  }

  return {
    feed: (pcm: Int16Array): void => {
      if (stopped) return
      // A backfill chunk can be a subarray view — send exactly its window, not
      // the full underlying 8KB buffer (which would include pre-key-down samples
      // the trim exists to exclude). Steady-state chunks stay zero-copy.
      const exact =
        pcm.byteOffset === 0 && pcm.byteLength === pcm.buffer.byteLength
          ? (pcm.buffer as ArrayBuffer)
          : (pcm.buffer as ArrayBuffer).slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength)
      window.omi.listenFeed(sessionId, exact)
    },
    finalize: (): void => {
      if (stopped) return
      window.omi.listenFinalize(sessionId)
    },
    stop: (): void => {
      if (stopped) return
      stopped = true
      over = true // a stop is not a death — suppress onDead from the close echo
      unsub()
      void window.omi.listenStop(sessionId)
    }
  }
}

// Spoken-language feed-forward (A3). Default behavior is INERT: with no
// `voiceLanguages` set, every turn uses the static `getPreferences().language`,
// byte-identical to before. When the user pins a candidate set, we remember the
// last provider-detected language (only when it is within that set) and hint it
// on the NEXT turn — the realtime provider frequently mislabels short PTT
// utterances (e.g. Russian rendered as Italian), and biasing toward a language
// the user actually speaks corrects it.
//
// Deliberately NOT ported from macOS PTTLanguageIdentifier: on-device ASR
// language ID and same-turn dual-transcript reconciliation — the Windows app
// ships no on-device multilingual model, so there is nothing to reconcile
// against within a turn. Feed-forward across turns is the achievable subset.
let lastDetectedLanguage: string | null = null

function resolveTranscribeLanguage(): string {
  const prefs = getPreferences()
  const candidates = prefs.voiceLanguages ?? []
  if (candidates.length > 0 && lastDetectedLanguage && candidates.includes(lastDetectedLanguage)) {
    return lastDetectedLanguage
  }
  return prefs.language
}

function rememberDetectedLanguage(language: string | undefined): void {
  const candidates = getPreferences().voiceLanguages ?? []
  if (candidates.length === 0) return // inert — no feed-forward when unset
  if (language && candidates.includes(language)) lastDetectedLanguage = language
}

/** Test-only: clear the per-session detected-language memory. */
export function __resetPttLanguageMemoryForTests(): void {
  lastDetectedLanguage = null
}

/** POST the captured PCM to the batch transcription endpoint. Returns the
 *  transcript ('' when the backend heard nothing). One transparent retry on 401
 *  with a force-refreshed token (covers a just-expired cached token). */
export async function batchTranscribe(pcm: Int16Array, signal: AbortSignal): Promise<string> {
  // Belt: never POST an empty body — the backend 400s it ("No audio data
  // provided") and there is nothing to transcribe anyway. Callers gate on
  // voicedStats/gateDecision BEFORE reaching here; this guards any future lane
  // that forgets (the first-press-after-idle zero-capture field bug shipped
  // exactly that way through the hub cascade).
  if (pcm.length === 0) return ''
  // Best-effort vocabulary boosting (A2): consume the terms collected at
  // hold-start (see startPttKeywordCollection) and ship them as the `keywords`
  // hint. Never load-bearing — consumePttKeywords is bounded and swallows every
  // source failure, and the param always carries at least the "Omi,OMI" brand
  // prepend. Consumed once here so a 401 retry reuses it rather than re-collecting.
  const keywords = pttKeywordsParam(await consumePttKeywords())

  const post = (): Promise<{ data?: { transcript?: string; language?: string } }> =>
    omiApi.post(BATCH_TRANSCRIBE_PATH, pcm.buffer, {
      params: batchTranscribeParams(resolveTranscribeLanguage(), keywords),
      headers: { 'Content-Type': 'application/octet-stream' },
      timeout: BATCH_TIMEOUT_MS,
      signal,
      // The shared interceptor's 5x exponential 429 backoff would hang the
      // gesture for tens of seconds; PTT wants an instant friendly message.
      __noRetry: true
    } as Parameters<typeof omiApi.post>[2])

  try {
    const res = await post()
    rememberDetectedLanguage(res.data?.language)
    return res.data?.transcript ?? ''
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 401 && auth.currentUser) {
      await auth.currentUser.getIdToken(true)
      const res = await post()
      rememberDetectedLanguage(res.data?.language)
      return res.data?.transcript ?? ''
    }
    throw err
  }
}

/** Map a batch failure to the friendly strip message. */
export function batchErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status
    if (status === 402) return 'Voice transcription needs an active Omi plan'
    if (status === 413) return RECORDING_TOO_LONG_MESSAGE
    if (status === 429) return 'Voice limit reached — try again in a minute'
    if (status === 401 || status === 403) return 'Sign-in expired — sign in again to use voice'
  }
  return 'Transcription failed — check your connection'
}
