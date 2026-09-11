// GPT-Live-1 continuous realtime lane over WebSocket.
//
// Unlike the Gemini lane (SDK) and the legacy OpenAI lane (WebRTC), GPT-Live-1 is
// a full-duplex text-JSON WebSocket: 24kHz PCM16 mono up via
// `session.input_audio.append`, 24kHz PCM16 mono down via
// `session.output_audio.delta`, and transcript deltas both ways. The server owns
// turn detection, so there is no input commit / response.create.
//
// Auth mirrors the hub lane: managed sessions go through the Omi relay with the
// Omi-auth token as a `token` query param (the relay injects the OpenAI key); BYOK
// connects direct to `wss://api.openai.com/v1/live/sessions` with the user's key in
// the `openai-insecure-api-key.<key>` subprotocol.
//
// The protocol exposes no per-turn completion event, so assistant transcript text
// is accumulated and reported to the capture record as one source utterance when
// the session ends (manual stop or `session.closed`) — matching the web client's
// `flushExchange`. A server turn-complete event (or a text-input frame for
// `sendUserText`) is a follow-up.

import { acquireMicStream } from '../audio'
import { makePipelineHandle } from '../capture/pipelineHandle'
import { createPcmPipeline as createWorkletPipeline } from '../capture/pcmPipeline'
import { createVoicePlayer, int16ToBase64, base64ToBytes, type VoicePlayer } from './pcmPlayer'
import { GPT_LIVE_MODEL } from './tokenMint'
import { mapGptLiveUsage } from './usageReport'
import { type ProviderSessionCallbacks, type ProviderSessionHandle } from './providerSession'
import { gptLiveRelayUrl, GPT_LIVE_VOICE } from './hub/gptLiveHubSession'

// 1024 samples @24kHz ≈ 43ms per uplink frame — low enough latency for
// conversation, large enough that base64+WS framing overhead stays trivial.
const UPLINK_FRAME_SAMPLES = 1024
const INPUT_SAMPLE_RATE = 24000

/** The one-time `session.start` frame (exported for wire tests). */
export function gptLiveSessionStartFrame(instructions: string): object {
  return {
    type: 'session.start',
    event_id: gptLiveEventId(),
    session: {
      model: GPT_LIVE_MODEL,
      instructions,
      audio: {
        format: { type: 'audio/pcm', rate: INPUT_SAMPLE_RATE },
        output: { voice: GPT_LIVE_VOICE }
      }
    }
  }
}

function gptLiveEventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `evt-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

type GptLiveServerMessage = {
  type?: string
  delta?: string
  message?: string
  error?: string | Record<string, unknown>
  interrupted?: boolean
  usage?: Parameters<typeof mapGptLiveUsage>[0]
}

export type GptLiveMessageHandler = {
  /** Parse + apply one server frame. */
  handle: (raw: string) => void
  /** Emit the accumulated assistant text as a source utterance and reset. */
  flush: () => void
}

/**
 * The GPT-Live onmessage handler, factored out of `startGptLiveSession` so its
 * audio/transcript bookkeeping is unit-testable without a live socket. `flush()`
 * reports the accumulated assistant reply (called on stop and `session.closed`).
 */
export function createGptLiveMessageHandler(deps: {
  isStopped: () => boolean
  getPlayer: () => VoicePlayer | null
  cb: ProviderSessionCallbacks
  /** Fired once when the server confirms `session.started`. */
  onStarted?: () => void
}): GptLiveMessageHandler {
  const { isStopped, getPlayer, cb } = deps
  let aiText = ''
  let utteranceSeq = 0

  const flush = (): void => {
    const text = aiText.trim()
    aiText = ''
    if (text && !isStopped()) cb.onUtterance(`gpt-live-turn-${utteranceSeq++}`, text)
  }

  const handle = (raw: string): void => {
    if (isStopped()) return
    let msg: GptLiveServerMessage
    try {
      msg = JSON.parse(raw) as GptLiveServerMessage
    } catch {
      return
    }
    const player = getPlayer()
    switch (msg.type) {
      case 'session.started':
        deps.onStarted?.()
        return
      case 'session.output_audio.delta':
        if (typeof msg.delta === 'string' && msg.delta.length > 0) {
          player?.enqueuePcm16(base64ToBytes(msg.delta))
        }
        return
      case 'session.input_transcript.delta':
        // The continuous lane's capture contract only records Omi's spoken reply;
        // the user transcript is surfaced by the ambient transcription lanes.
        return
      case 'session.output_transcript.delta':
        if (typeof msg.delta === 'string') aiText += msg.delta
        return
      case 'session.interrupted':
        player?.clear()
        aiText = ''
        return
      case 'session.closed': {
        if (msg.usage) {
          try {
            cb.onUsage(mapGptLiveUsage(msg.usage, GPT_LIVE_MODEL))
          } catch {
            /* usage is best-effort */
          }
        }
        flush()
        return
      }
      case 'error': {
        const err = msg.error
        const nested = typeof err === 'object' && err !== null ? err.message : undefined
        const message =
          (typeof msg.message === 'string' && msg.message) ||
          (typeof err === 'string' && err) ||
          (typeof nested === 'string' ? nested : 'GPT-Live realtime error')
        // The socket may stay open after an error frame; treat it as fatal so the
        // controller lands in the error state rather than hanging.
        cb.onFatal(message, true)
        return
      }
      default:
        if (msg.interrupted === true) {
          player?.clear()
          aiText = ''
        }
        return
    }
  }

  return { handle, flush }
}

export async function startGptLiveSession(args: {
  /** Omi-auth token for the relay (managed) or the OpenAI key (BYOK). */
  token: string
  /** When true, `token` is the user's OpenAI key and we connect direct. */
  byok?: boolean
  /** The assembled per-session system instruction (systemInstruction.ts). */
  instructions: string
  sinkId?: string
  cb: ProviderSessionCallbacks
}): Promise<ProviderSessionHandle> {
  const { cb } = args
  let stopped = false
  let muted = false
  let socket: WebSocket | null = null
  let player: VoicePlayer | null = null
  let mic: { stop: () => void } | null = null

  const stop = (): void => {
    if (stopped) return
    stopped = true
    mic?.stop()
    mic = null
    const ws = socket
    socket = null
    if (ws) {
      try {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'session.close' }))
      } catch {
        /* ignore */
      }
      try {
        ws.close()
      } catch {
        /* ignore */
      }
    }
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
      sampleRate: INPUT_SAMPLE_RATE,
      sinkId: args.sinkId,
      onStarted: () => {
        if (!stopped) cb.onSpeakingStart()
      },
      onDrained: () => {
        if (!stopped) cb.onSpeakingEnd()
      }
    })
  } catch (e) {
    throw new Error(`GPT-Live audio init failed: ${(e as Error)?.message ?? e}`)
  }

  await new Promise<void>((resolve, reject) => {
    const url = args.byok ? 'wss://api.openai.com/v1/live/sessions' : gptLiveRelayUrl(args.token)
    const protocols = args.byok ? [`openai-insecure-api-key.${args.token}`] : undefined
    const ws = new WebSocket(url, protocols)
    socket = ws
    let connected = false

    const startCapture = async (): Promise<void> => {
      if (stopped || mic) return
      const stream = await acquireMicStream()
      if (stopped) {
        stream.getTracks().forEach((t) => {
          try {
            t.stop()
          } catch {
            /* ignore */
          }
        })
        return
      }
      const feed = (pcm: Int16Array): void => {
        const active = socket
        if (stopped || muted || !active || active.readyState !== WebSocket.OPEN) return
        try {
          active.send(
            JSON.stringify({ type: 'session.input_audio.append', audio: int16ToBase64(pcm) })
          )
        } catch {
          /* socket mid-close — onclose handles the session end */
        }
      }
      mic = makePipelineHandle(
        stream,
        createWorkletPipeline(stream, feed, undefined, UPLINK_FRAME_SAMPLES, INPUT_SAMPLE_RATE)
      )
    }

    const handler = createGptLiveMessageHandler({
      isStopped: () => stopped,
      getPlayer: () => player,
      cb,
      onStarted: () => {
        if (connected || stopped) return
        void startCapture().then(
          () => {
            if (stopped || connected) return
            connected = true
            resolve()
            cb.onConnected()
          },
          (e: unknown) => {
            // Pre-ready failure: tear down and reject so startGptLiveSession
            // throws (the controller surfaces the fatal exactly once).
            stop()
            reject(e instanceof Error ? e : new Error(String(e)))
          }
        )
      }
    })

    ws.onopen = () => {
      try {
        ws.send(JSON.stringify(gptLiveSessionStartFrame(args.instructions)))
      } catch (e) {
        stop()
        reject(e instanceof Error ? e : new Error(String(e)))
      }
    }
    ws.onmessage = (e: MessageEvent) => {
      const data = typeof e.data === 'string' ? e.data : ''
      handler.handle(data)
    }
    ws.onerror = () => {
      if (connected) fail('GPT-Live connection failed', true)
      else {
        stop()
        reject(new Error('GPT-Live connection failed'))
      }
    }
    ws.onclose = (e: CloseEvent) => {
      const reason = `GPT-Live closed (${e.code})${e.reason ? ` ${e.reason}` : ''}`
      if (connected) fail(reason, true)
      else {
        stop()
        reject(new Error(reason))
      }
    }
  })

  if (stopped) throw new Error('voice session stopped during connect')

  return {
    stop,
    setMuted: (m: boolean): void => {
      muted = m
    },
    setOutputDevice: async (deviceId: string): Promise<void> => {
      await player?.setSinkId(deviceId)
    },
    sendUserText: (_text: string): void => {
      // GPT-Live's protocol has no text-input frame (web parity); typed turns in
      // a live continuous session are a follow-up.
    }
  }
}
