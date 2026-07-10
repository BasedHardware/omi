import { useEffect } from 'react'
import { createPcmPipeline, createVadGate, type PcmPipeline, type VadGate } from './engine'
import { getSystemAudioStream } from '../lib/capture/systemAudio'
import { acquireMicStream } from '../lib/audio'
import type { CaptureGating, ListenSource } from '../../../shared/types'

// The capture window's continuous-audio engine. Serves audio-start / audio-stop
// commands (from the capture window's own continuous-mic lane and from UI screen
// sessions): acquires the source stream, runs it through the PCM pipeline and
// (optionally) the VAD gate, and forwards gated PCM to the main-process WebSocket
// via window.omi.listenFeed(sessionId, chunk). The main process routes transcript
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
  stream: MediaStream | null
  // Set if audio-stop lands while the source stream is still being acquired, so
  // the resolved stream is torn down instead of leaking.
  stopped: boolean
}

const sessions = new Map<string, AudioSession>()

/** Acquire the mic. Test harnesses (OMI_ALLOW_VIRTUAL_MIC=1) feed a VB-Cable as
 *  the input, so skip the virtual-device steering acquireMicStream applies. */
async function acquireMic(): Promise<MediaStream> {
  if (window.omi?.allowVirtualMic) return navigator.mediaDevices.getUserMedia({ audio: true })
  return acquireMicStream()
}

async function startAudioSession(
  sessionId: string,
  source: ListenSource,
  gating: CaptureGating,
  ownerId: number
): Promise<void> {
  if (sessions.has(sessionId)) return // idempotent — duplicate/StrictMode command
  const session: AudioSession = {
    ownerId,
    pipeline: null,
    gate: null,
    stream: null,
    stopped: false
  }
  sessions.set(sessionId, session)

  let stream: MediaStream
  try {
    stream = source === 'mic' ? await acquireMic() : await getSystemAudioStream()
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
  session.stream = stream

  const feed = (pcm: Int16Array): void =>
    window.omi?.listenFeed(sessionId, pcm.buffer as ArrayBuffer)
  if (gating === 'vad') {
    const gate = createVadGate({
      onVoiced: feed,
      onStatus: (mode, reason) => window.omi?.captureEmit({ type: 'vad-status', mode, reason })
    })
    session.gate = gate
    session.pipeline = createPcmPipeline(stream, (pcm) => gate.push(pcm))
  } else {
    session.pipeline = createPcmPipeline(stream, feed)
  }
}

function stopAudioSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s) return
  s.stopped = true
  s.pipeline?.stop() // tears down the graph and stops the stream tracks
  s.gate?.stop()
  // Belt-and-suspenders if the pipeline never got created (stop during acquire):
  s.stream?.getTracks().forEach((t) => t.stop())
  sessions.delete(sessionId)
}

/** Mounted once in CaptureApp. Only owns the command subscription; all session
 *  state lives in the module singleton above. */
export function AudioSessionHost(): null {
  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd, ownerId) => {
      if (cmd.type === 'audio-start') {
        void startAudioSession(cmd.sessionId, cmd.source, cmd.gating, ownerId)
      } else if (cmd.type === 'audio-stop') {
        stopAudioSession(cmd.sessionId)
      }
    })
  }, [])
  return null
}
