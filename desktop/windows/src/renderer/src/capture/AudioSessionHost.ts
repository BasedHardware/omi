import { useEffect } from 'react'
import {
  createPcmPipeline,
  createVadGate,
  type PcmPipeline,
  type VadGate
} from '../lib/capture/captureEngine'
import { resolveVadGateMode } from '../lib/capture/vadGate'
import { getPreferences } from '../lib/preferences'
import { getSystemAudioStream } from '../lib/capture/systemAudio'
import {
  createLoopbackMusicFilter,
  type LoopbackMusicFilter
} from '../lib/capture/loopbackMusicFilter'
import { acquireMicStream } from '../lib/audio'
import { assistantGate, wrapFeed } from './assistantGate'
import type { ListenSource } from '../../../shared/types'

// The capture window's continuous-audio engine. Serves audio-start / audio-stop
// commands (from the capture window's own continuous-mic lane and from UI screen
// sessions): acquires the source stream, runs it through the PCM pipeline and the
// VAD gate, and forwards gated PCM to the main-process WebSocket via
// window.omi.listenFeed(sessionId, chunk). The main process routes transcript
// messages back to whichever window opened the listen session (its ownerId), so
// audio origin (here) and transcript destination decouple.
//
// Module-singleton session map keyed by sessionId so the command server is
// idempotent under React StrictMode double-mount / duplicate commands; the
// component only owns the command subscription.

type AudioSession = {
  ownerId: number
  pipeline: PcmPipeline | null
  gate: VadGate | null
  // Loopback lane only: YAMNet speech/music filter between the VAD gate and the
  // WebSocket feed (a confident music verdict drops the audio).
  musicFilter: LoopbackMusicFilter | null
  // Set if audio-stop lands while the source stream is still being acquired, so
  // the resolved stream is torn down instead of leaking.
  stopped: boolean
}

const sessions = new Map<string, AudioSession>()

async function startAudioSession(
  sessionId: string,
  source: ListenSource,
  ownerId: number
): Promise<void> {
  if (sessions.has(sessionId)) return // idempotent — duplicate/StrictMode command
  const session: AudioSession = {
    ownerId,
    pipeline: null,
    gate: null,
    musicFilter: null,
    stopped: false
  }
  sessions.set(sessionId, session)

  let stream: MediaStream
  try {
    stream = source === 'mic' ? await acquireMicStream() : await getSystemAudioStream()
  } catch (e) {
    sessions.delete(sessionId)
    const err = e as Error
    // Route the source failure back to the window that opened the session so it
    // can surface a mic/loopback error (same shape omiListenClient expects).
    window.omi?.captureEmit(
      { type: 'audio-source-error', sessionId, name: err.name, message: err.message },
      ownerId
    )
    return
  }

  // audio-stop arrived while acquiring — drop the just-opened stream.
  if (session.stopped) {
    stream.getTracks().forEach((t) => t.stop())
    sessions.delete(sessionId)
    return
  }

  const feed = (pcm: Int16Array): void =>
    window.omi?.listenFeed(sessionId, pcm.buffer as ArrayBuffer)
  // Loopback lane: classify VAD-gated windows (YAMNet) so a confident music
  // verdict closes the lane — ambient/meeting capture never transcribes a
  // movie. The mic lane never classifies (the user's own voice always counts).
  let onVoiced = feed
  if (source !== 'mic') {
    const filter = createLoopbackMusicFilter(feed)
    session.musicFilter = filter
    onVoiced = filter.push
  }
  // Read the local-VAD-gate preference at session start (Settings → Transcription).
  // Disabled → passthrough, so every frame reaches the backend ungated.
  const gate = createVadGate({
    onVoiced,
    mode: resolveVadGateMode(getPreferences().vadGateEnabled)
  })
  session.gate = gate
  // Echo gate (Phase 6): while Omi's voice plays, drop frames BEFORE the VAD
  // gate so Omi's speech never enters the pre-roll ring either. Applies to both
  // lanes — mic (acoustic echo) and system audio (Omi's voice IS system output).
  session.pipeline = createPcmPipeline(
    stream,
    wrapFeed((pcm) => gate.push(pcm))
  )
}

/** Test-only (read via the OMI_E2E-gated capture hook): current music-gate
 *  verdict of each active loopback session. Empty when no loopback lane runs. */
export function _loopbackVerdictsForTest(): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [id, s] of sessions) {
    if (s.musicFilter) out[id] = s.musicFilter.verdict()
  }
  return out
}

function stopAudioSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s) return
  s.stopped = true
  s.pipeline?.stop() // tears down the graph and stops the stream tracks
  s.gate?.stop()
  s.musicFilter?.stop()
  sessions.delete(sessionId)
}

/** Mounted once in CaptureApp. Only owns the command subscription; all session
 *  state lives in the module singleton above. */
export function AudioSessionHost(): null {
  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd, ownerId) => {
      if (cmd.type === 'audio-start') {
        void startAudioSession(cmd.sessionId, cmd.source, ownerId)
      } else if (cmd.type === 'audio-stop') {
        stopAudioSession(cmd.sessionId)
      } else if (cmd.type === 'assistant-speaking') {
        // Echo gate: the voice surface owns the timing (incl. the release
        // hangover); this window just enforces the final boolean on all
        // continuous feeds via wrapFeed above.
        assistantGate.setSpeaking(cmd.active)
      }
    })
  }, [])
  return null
}
