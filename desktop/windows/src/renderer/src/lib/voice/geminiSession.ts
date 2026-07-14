// Gemini Live lane over WebSocket (Phase 6). Unlike the OpenAI WebRTC lane,
// we own the audio path: 16kHz Int16 PCM up (reusing the Phase 2 worklet
// capture pipeline at a 64ms frame), 24kHz PCM down through the jitter-buffered
// AudioWorklet player (~150ms cushion, clear-buffer-on-interrupt). The ephemeral
// 'auth_tokens/…' name minted by the backend is used as the SDK apiKey on
// v1alpha (the SDK connects to the constrained Live WS with it).
//
// Barge-in: the provider's server VAD interrupts generation; the interrupted
// flag clears the local playback buffer AND gates the interrupted generation's
// trailing audio (see createGeminiMessageHandler). The mic is never gated.

import { GoogleGenAI, Modality, type Session, type LiveServerMessage } from '@google/genai'
import { acquireMicStream } from '../audio'
import { makePipelineHandle } from '../capture/pipelineHandle'
import { createPcmPipeline as createWorkletPipeline } from '../capture/pcmPipeline'
import { createVoicePlayer, int16ToBase64, base64ToBytes, type VoicePlayer } from './pcmPlayer'
import { GEMINI_LIVE_MODEL } from './tokenMint'
import { mapGeminiUsage, usageDelta, usageTotal, type RealtimeUsageBody } from './usageReport'
import {
  OMI_VOICE_INSTRUCTIONS,
  type ProviderSessionCallbacks,
  type ProviderSessionHandle
} from './providerSession'

// 1024 samples @16kHz = 64ms per uplink frame — low enough latency for
// conversation, big enough that base64+WS framing overhead stays trivial.
const UPLINK_FRAME_SAMPLES = 1024

// The Gemini Live onmessage handler, factored out of startGeminiSession so its
// barge-in gating is unit-testable without a live socket. Owns the per-turn
// text/usage bookkeeping; `getPlayer`/`isStopped` read the live session state
// (player is nulled on stop) so a late message after teardown is a no-op.
export function createGeminiMessageHandler(deps: {
  isStopped: () => boolean
  getPlayer: () => VoicePlayer | null
  cb: ProviderSessionCallbacks
}): (msg: LiveServerMessage) => void {
  const { isStopped, getPlayer, cb } = deps
  let turnText = ''
  let turnSeq = 0
  // Gemini's usageMetadata is a RUNNING total re-sent across messages — report
  // only the field-wise DELTA since the last snapshot so the ledger isn't
  // over-counted (the OpenAI lane reports once, at stop, instead).
  let lastUsage: RealtimeUsageBody | null = null
  // Barge-in gate. Gemini keeps streaming a few trailing PCM parts AFTER it
  // signals serverContent.interrupted for the barged-in generation; player.clear()
  // only flushes what is already queued, so without this gate those later chunks
  // get re-enqueued and bleed stale audio over the user. Mirrors Mac's
  // geminiResponsePending hard gate (RealtimeHubSession.swift): closed the instant
  // interrupt fires, re-opened at the next turn boundary (turnComplete) so the
  // FOLLOWING generation's audio plays normally.
  let interruptedTurnActive = false

  return (msg: LiveServerMessage): void => {
    if (isStopped()) return
    const player = getPlayer()
    const sc = msg.serverContent
    if (sc?.interrupted) {
      // Barge-in: stale audio must never keep playing over the user — flush what
      // is queued and drop any trailing chunks for this now-dead generation.
      interruptedTurnActive = true
      player?.clear()
    }
    for (const part of sc?.modelTurn?.parts ?? []) {
      const data = part.inlineData?.data
      if (typeof data === 'string' && data.length > 0 && !interruptedTurnActive) {
        player?.enqueuePcm16(base64ToBytes(data))
      }
    }
    if (sc?.outputTranscription?.text) turnText += sc.outputTranscription.text
    if (sc?.turnComplete) {
      // Turn boundary: the (possibly interrupted) generation is closed — re-open
      // the gate so the next generation's audio plays, and play any sub-cushion tail.
      interruptedTurnActive = false
      player?.flush()
      const text = turnText
      turnText = ''
      if (text.trim()) cb.onUtterance(`gemini-turn-${turnSeq++}`, text)
    }
    if (msg.usageMetadata) {
      const cumulative = mapGeminiUsage(msg.usageMetadata, GEMINI_LIVE_MODEL)
      const delta = usageDelta(cumulative, lastUsage)
      lastUsage = cumulative
      if (usageTotal(delta) > 0) cb.onUsage(delta)
    }
  }
}

export async function startGeminiSession(args: {
  authToken: string
  sinkId?: string
  cb: ProviderSessionCallbacks
}): Promise<ProviderSessionHandle> {
  const { cb } = args
  let stopped = false
  let muted = false
  let session: Session | null = null
  let player: VoicePlayer | null = null
  let mic: { stop: () => void } | null = null

  const stop = (): void => {
    if (stopped) return
    stopped = true
    mic?.stop()
    mic = null
    try {
      session?.close()
    } catch {
      /* ignore */
    }
    session = null
    player?.close()
    player = null
  }

  const fail = (message: string, retryable: boolean): void => {
    if (stopped) return
    stop()
    cb.onFatal(message, retryable)
  }

  try {
    player = await createVoicePlayer({
      sinkId: args.sinkId,
      onStarted: () => {
        if (!stopped) cb.onSpeakingStart()
      },
      onDrained: () => {
        if (!stopped) cb.onSpeakingEnd()
      }
    })

    const ai = new GoogleGenAI({
      apiKey: args.authToken,
      httpOptions: { apiVersion: 'v1alpha' }
    })

    session = await ai.live.connect({
      model: GEMINI_LIVE_MODEL,
      config: {
        responseModalities: [Modality.AUDIO],
        systemInstruction: OMI_VOICE_INSTRUCTIONS,
        // Omi's spoken words as SOURCE text for the injected record.
        outputAudioTranscription: {}
      },
      callbacks: {
        onmessage: createGeminiMessageHandler({
          isStopped: () => stopped,
          getPlayer: () => player,
          cb
        }),
        onerror: (e: ErrorEvent) => fail(`Gemini live error: ${e.message || 'socket error'}`, true),
        onclose: (e: CloseEvent) =>
          fail(`Gemini live closed (${e.code})${e.reason ? ` ${e.reason}` : ''}`, true)
      }
    })

    // Mic uplink: the same worklet capture pipeline the Phase 2 lanes use
    // (16kHz Int16 frames), wrapped so stop() reliably releases the mic.
    const stream = await acquireMicStream()
    const feed = (pcm: Int16Array): void => {
      if (stopped || muted || !session) return
      try {
        session.sendRealtimeInput({
          audio: { data: int16ToBase64(pcm), mimeType: 'audio/pcm;rate=16000' }
        })
      } catch {
        /* socket mid-close — onclose handles the session end */
      }
    }
    mic = makePipelineHandle(
      stream,
      createWorkletPipeline(stream, feed, undefined, UPLINK_FRAME_SAMPLES)
    )
  } catch (e) {
    stop()
    throw new Error(`Gemini live connect failed: ${(e as Error)?.message ?? e}`)
  }

  if (stopped) throw new Error('voice session stopped during connect')
  cb.onConnected()

  return {
    stop,
    setMuted: (m: boolean): void => {
      muted = m
    },
    setOutputDevice: async (deviceId: string): Promise<void> => {
      await player?.setSinkId(deviceId)
    },
    sendUserText: (text: string): void => {
      if (stopped || !session) return
      try {
        session.sendRealtimeInput({ text })
      } catch {
        /* socket mid-close */
      }
    }
  }
}
