// OpenAI Realtime lane over WebRTC (Phase 6). Chromium owns the hard parts —
// Opus, jitter, and wiring the remote track as the AEC far-end reference — so
// this wrapper is thin: our own <audio> element (so setSinkId can follow the
// user's output device), our own mic stream (virtual-device steering from
// lib/audio), far_field noise reduction when playing on speakers, and event
// adaptation to the provider-blind ProviderSessionCallbacks.
//
// Barge-in is the provider's server VAD: the mic is NEVER gated locally — the
// echo gate only pauses the separate always-on transcription lanes.

import { RealtimeAgent, RealtimeSession, OpenAIRealtimeWebRTC } from '@openai/agents-realtime'
import type { RealtimeItem } from '@openai/agents-realtime'
import { acquireMicStream } from '../audio'
import { OPENAI_REALTIME_MODEL } from './tokenMint'
import { mapOpenAiUsage } from './usageReport'
import {
  OMI_VOICE_INSTRUCTIONS,
  type ProviderSessionCallbacks,
  type ProviderSessionHandle
} from './providerSession'

/** Text of a completed assistant message item (source text — audio transcript
 *  or output text), or null while still in progress / empty. */
export function completedAssistantText(item: RealtimeItem): string | null {
  if (item.type !== 'message' || item.role !== 'assistant') return null
  if (item.status !== 'completed') return null
  const text = item.content
    .map((c) => {
      if (c.type === 'output_audio') return c.transcript ?? ''
      if (c.type === 'output_text') return c.text
      return ''
    })
    .join(' ')
    .trim()
  return text.length > 0 ? text : null
}

export async function startOpenAiSession(args: {
  clientSecret: string
  /** true when Omi's voice plays on open speakers (far_field noise reduction). */
  onSpeakers: boolean
  sinkId?: string
  cb: ProviderSessionCallbacks
}): Promise<ProviderSessionHandle> {
  const { cb } = args
  let stopped = false
  const emittedUtterances = new Set<string>()

  const audioElement = document.createElement('audio')
  audioElement.autoplay = true
  if (args.sinkId) {
    await audioElement.setSinkId(args.sinkId).catch(() => {
      /* unknown device — stay on default */
    })
  }

  const mediaStream = await acquireMicStream()
  const transport = new OpenAIRealtimeWebRTC({ mediaStream, audioElement })
  const agent = new RealtimeAgent({ name: 'Omi', instructions: OMI_VOICE_INSTRUCTIONS })
  const session = new RealtimeSession(agent, {
    transport,
    model: OPENAI_REALTIME_MODEL,
    config: {
      outputModalities: ['audio'],
      audio: {
        input: {
          // On speakers the mic hears the room (and Omi) — far_field matches.
          // On a headset the near_field default is correct.
          noiseReduction: args.onSpeakers ? { type: 'far_field' } : { type: 'near_field' }
        }
      }
    }
  })

  session.on('audio_start', () => {
    if (!stopped) cb.onSpeakingStart()
  })
  session.on('audio_stopped', () => {
    if (!stopped) cb.onSpeakingEnd()
  })
  session.on('audio_interrupted', () => {
    if (!stopped) cb.onSpeakingEnd()
  })
  session.on('history_updated', (history: RealtimeItem[]) => {
    if (stopped) return
    for (const item of history) {
      const id = 'itemId' in item ? item.itemId : undefined
      if (!id || emittedUtterances.has(id)) continue
      const text = completedAssistantText(item)
      if (text === null) continue
      emittedUtterances.add(id)
      cb.onUtterance(id, text)
    }
  })
  session.on('error', (e) => {
    // Non-fatal server errors surface here too; connection loss is what ends
    // the session (connection_change below). Log for diagnosis only.
    console.warn('[voice:openai] session error:', e)
  })
  session.transport.on('connection_change', (status) => {
    if (stopped) return
    if (status === 'disconnected') {
      cb.onFatal('realtime connection lost', true)
    }
  })

  const stop = (): void => {
    if (stopped) return
    stopped = true
    // Final cumulative usage → ledger (managed sessions only report once).
    try {
      cb.onUsage(mapOpenAiUsage(session.usage, OPENAI_REALTIME_MODEL))
    } catch {
      /* usage is best-effort */
    }
    try {
      session.close()
    } catch {
      /* ignore */
    }
    // The SDK doesn't own tracks we provided — release the mic ourselves.
    mediaStream.getTracks().forEach((t) => {
      try {
        t.stop()
      } catch {
        /* ignore */
      }
    })
    audioElement.srcObject = null
  }

  try {
    await session.connect({ apiKey: args.clientSecret })
  } catch (e) {
    stop()
    throw new Error(`OpenAI realtime connect failed: ${(e as Error)?.message ?? e}`)
  }
  if (stopped) throw new Error('voice session stopped during connect')
  cb.onConnected()

  return {
    stop,
    setMuted: (muted: boolean): void => {
      try {
        session.mute(muted)
      } catch {
        /* transport gone mid-teardown */
      }
    },
    setOutputDevice: async (deviceId: string): Promise<void> => {
      await audioElement.setSinkId(deviceId)
    },
    sendUserText: (text: string): void => {
      session.sendMessage(text)
    }
  }
}
