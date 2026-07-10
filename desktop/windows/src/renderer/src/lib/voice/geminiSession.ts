// Gemini Live lane over WebSocket (Phase 6). Unlike the OpenAI WebRTC lane,
// we own the audio path: 16kHz Int16 PCM up (reusing the Phase 2 worklet
// capture pipeline at a 64ms frame), 24kHz PCM down through the jitter-buffered
// AudioWorklet player (~150ms cushion, clear-buffer-on-interrupt). The ephemeral
// 'auth_tokens/…' name minted by the backend is used as the SDK apiKey on
// v1alpha (the SDK connects to the constrained Live WS with it).
//
// Barge-in: the provider's server VAD interrupts generation; the interrupted
// flag clears the local playback buffer instantly. The mic is never gated.

import { GoogleGenAI, Modality, type Session, type LiveServerMessage } from '@google/genai'
import { acquireMicStream } from '../audio'
import { makePipelineHandle } from '../capture/pipelineHandle'
import { createPcmPipeline as createWorkletPipeline } from '../capture/pcmPipeline'
import { createVoicePlayer, int16ToBase64, base64ToBytes, type VoicePlayer } from './pcmPlayer'
import { GEMINI_LIVE_MODEL } from './tokenMint'
import { mapGeminiUsage } from './usageReport'
import {
  OMI_VOICE_INSTRUCTIONS,
  type ProviderSessionCallbacks,
  type ProviderSessionHandle
} from './providerSession'

// 1024 samples @16kHz = 64ms per uplink frame — low enough latency for
// conversation, big enough that base64+WS framing overhead stays trivial.
const UPLINK_FRAME_SAMPLES = 1024

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
  let turnText = ''
  let turnSeq = 0

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
        onmessage: (msg: LiveServerMessage) => {
          if (stopped) return
          const sc = msg.serverContent
          if (sc?.interrupted) {
            // Barge-in: stale audio must never keep playing over the user.
            player?.clear()
          }
          for (const part of sc?.modelTurn?.parts ?? []) {
            const data = part.inlineData?.data
            if (typeof data === 'string' && data.length > 0) {
              player?.enqueuePcm16(base64ToBytes(data))
            }
          }
          if (sc?.outputTranscription?.text) turnText += sc.outputTranscription.text
          if (sc?.turnComplete) {
            const text = turnText
            turnText = ''
            if (text.trim()) cb.onUtterance(`gemini-turn-${turnSeq++}`, text)
          }
          if (msg.usageMetadata) {
            cb.onUsage(mapGeminiUsage(msg.usageMetadata, GEMINI_LIVE_MODEL))
          }
        },
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
