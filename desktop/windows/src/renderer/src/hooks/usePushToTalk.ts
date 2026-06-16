import { useEffect, useRef, useState } from 'react'
import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import type { TranscriptLine } from '../../../shared/types'
import {
  HOLD_THRESHOLD_MS,
  assembleTranscript,
  upsertLine,
  shouldFinalize,
  type FinalizeConfig
} from '../components/overlay/pushToTalk'

// After Space is released we keep the mic + transcription stream OPEN and decide
// when to commit from live signals (see shouldFinalize), rather than a fixed delay:
//  - VAD watches the mic so we wait until you've actually STOPPED talking, then
//  - wait for the backend's trailing FINAL segment (v4/listen lags ~1.8s, no interim)
//    to land and settle. If you held long enough that it already arrived, this is
//    immediate. A capture that produced nothing ends fast; a hard cap always ends it.
const FINALIZE_CFG: FinalizeConfig = {
  maxMs: 6000,
  noVoiceGraceMs: 700,
  silenceMs: 350,
  settleMs: 400,
  // Balanced: hold the commit ~1s after release so Omi's ~1.8s-late trailing
  // segment usually lands before we send (catches the tail most of the time),
  // without making every voice message wait out the full backend lag.
  trailingGraceMs: 1000
}
const POLL_MS = 120
// Mic energy this far above its adaptive noise floor counts as speech (VAD). The
// floor learns steady noise (fans), so they don't register as voice.
const VOICE_MARGIN = 0.08

type Options = {
  /** Final transcript on hold-release (non-empty only) — caller auto-sends it. */
  onCommit: (text: string) => void
  /** Live transcript as it's recognized (during the hold and the finalize wait), so
   *  the caller can render it in the input box before it's sent. Fires '' at the
   *  start of a capture to clear any leftover. */
  onTranscript: (text: string) => void
  /** Fires when a hold-capture finalizes, whether or not it produced any
   *  transcript. Lets a caller treat the GESTURE as complete even when cloud
   *  transcription was unavailable (e.g. quota/1008 closed the socket) — used by
   *  onboarding so a no-quota account isn't dead-ended on "hold Space and speak". */
  onCaptureEnd?: () => void
  /** Restore the input to its pre-hold contents, removing the space(s) that were
   *  typed while the key was held. Receives the snapshot captured at key-down. */
  restoreDraft: (snapshot: string) => void
  /** Current draft text, read at key-down for the window-level (textarea-unfocused)
   *  hold path so the snapshot/restore matches the focused path. */
  getDraft: () => string
}

export type PushToTalk = {
  recording: boolean
  /** True after release while we wait for the backend's final transcript to land. */
  finalizing: boolean
  error: string | null
  /** Live analyser for the waveform visualizer (null while not capturing). */
  analyserRef: React.MutableRefObject<AnalyserNode | null>
  /** Wire to the input's onKeyDown. Returns true if it consumed the event (the
   *  caller must then NOT run its own Enter/typing handling). */
  onKeyDown: (e: React.KeyboardEvent) => boolean
  /** Wire to the input's onKeyUp. Returns true if it consumed the event. */
  onKeyUp: (e: React.KeyboardEvent) => boolean
  /** Abort an in-progress recording OR pending finalize WITHOUT sending
   *  (Esc / focus loss / unmount). */
  cancel: () => void
}

function isSpace(e: React.KeyboardEvent): boolean {
  return e.key === ' ' || e.code === 'Space'
}

/**
 * Hold-Space-to-talk for the overlay's Ask box. A quick Space tap types a space as
 * usual; holding past HOLD_THRESHOLD_MS starts mic transcription (Omi v4/listen,
 * via startTranscription) and exposes a live analyser for
 * the waveform. Releasing enters a VAD-gated finalize phase that waits until you've
 * stopped speaking and the backend's transcript has settled, then auto-sends it.
 * Normal typing stays fully native — the space is only "taken back" (draft restored
 * to the key-down snapshot) once a hold actually crosses the threshold.
 */
export function usePushToTalk(opts: Options): PushToTalk {
  const { onCommit, onTranscript, restoreDraft } = opts
  const [recording, setRecording] = useState(false)
  const [finalizing, setFinalizing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Mirrors `recording` for synchronous reads inside event handlers / async work.
  const recordingRef = useRef(false)
  // Mirrors `finalizing` for synchronous reads.
  const finalizingRef = useRef(false)
  // Pending hold timer (set on key-down, fires to start recording, cleared on a tap).
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Draft value captured at key-down (before the space is inserted).
  const snapshotRef = useRef('')
  // Generation token: every start bumps it so async work (transcription connect,
  // finalize poll, VAD) from a superseded session no-ops / tears itself down.
  const sessionRef = useRef(0)

  const handleRef = useRef<TranscriptionHandle | null>(null)
  const linesRef = useRef<TranscriptLine[]>([])
  const interimRef = useRef('')
  // Timestamp (ms) of the last accepted segment THIS hold, or 0 if none yet.
  const lastSegmentAtRef = useRef(0)
  // VAD: last time the mic had speech-level energy, and whether it ever did.
  const lastVoiceAtRef = useRef(0)
  const everVoicedRef = useRef(false)
  // Segment ids already consumed by PRIOR holds. The v4/listen backend keeps a
  // server-side conversation and RE-SENDS earlier segments (same id) on each new
  // connection, so without this an old utterance bleeds into the next message. Any
  // id seen in a previous, finished hold is skipped as an echo.
  const consumedIdsRef = useRef<Set<string>>(new Set())

  // Poll timer for the finalize phase.
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Mic audio graph (a second stream, independent of transcription's), feeding both
  // the waveform and the VAD.
  const analyserRef = useRef<AnalyserNode | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const clearPoll = (): void => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  const stopAudioViz = (): void => {
    analyserRef.current = null // also stops the VAD loop (it checks this ref)
    if (ctxRef.current) {
      void ctxRef.current.close().catch(() => {})
      ctxRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }

  const startAudioViz = async (session: number): Promise<void> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      // Superseded OR already released while awaiting permission — drop the stream so
      // a fast key-drop doesn't leave the mic open.
      if (sessionRef.current !== session || !recordingRef.current) {
        stream.getTracks().forEach((t) => t.stop())
        return
      }
      streamRef.current = stream
      const ctx = new AudioContext()
      ctxRef.current = ctx
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 64 // 32 frequency bins; the visualizer uses the low end
      // Higher = smoother, less jumpy bars (averages more across frames). The
      // visualizer also eases each bar toward its target, so speech ramps in.
      analyser.smoothingTimeConstant = 0.85
      ctx.createMediaStreamSource(stream).connect(analyser)
      analyserRef.current = analyser

      // Voice-activity detection on the same analyser: mark the last time the mic had
      // energy above its adaptive noise floor (so steady fans don't count as voice).
      const buf = new Uint8Array(analyser.frequencyBinCount)
      const n = Math.min(24, buf.length)
      let floor = 0
      let seeded = false
      const vad = (): void => {
        if (analyserRef.current !== analyser) return // viz stopped → end the loop
        analyser.getByteFrequencyData(buf)
        let sum = 0
        for (let i = 0; i < n; i++) sum += buf[i] / 255
        const level = sum / n
        if (!seeded) {
          floor = level
          seeded = true
        } else {
          floor = level > floor ? floor * 0.97 + level * 0.03 : floor * 0.9 + level * 0.1
        }
        if (level - floor > VOICE_MARGIN) {
          lastVoiceAtRef.current = Date.now()
          everVoicedRef.current = true
        }
        requestAnimationFrame(vad)
      }
      requestAnimationFrame(vad)
    } catch {
      // Waveform/VAD are non-essential; a blocked mic just shows flat bars and lets
      // the finalize fall back to the segment-settle / max-cap path. Transcription
      // has its own mic + error surfacing.
    }
  }

  // Remember this hold's segment ids so the backend re-sending them on a later
  // connection is recognized as an echo and skipped.
  const markConsumed = (): void => {
    for (const ln of linesRef.current) if (ln.id != null) consumedIdsRef.current.add(ln.id)
  }

  // Stop and discard the current capture + buffered transcript, and invalidate the
  // session so any in-flight async work tears itself down.
  const teardownTranscription = (): void => {
    clearPoll()
    finalizingRef.current = false
    setFinalizing(false)
    stopAudioViz()
    try {
      handleRef.current?.stop()
    } catch {
      /* ignore */
    }
    handleRef.current = null
    markConsumed()
    linesRef.current = []
    interimRef.current = ''
    sessionRef.current++
  }

  const startRecording = (): void => {
    // Abandon any prior, not-yet-committed utterance (e.g. a quick re-hold during
    // the finalize window) before starting fresh.
    teardownTranscription()

    const session = ++sessionRef.current
    recordingRef.current = true
    setRecording(true)
    setError(null)
    // Take back the space(s) auto-repeat inserted while holding, then clear the box
    // so the recognized transcript renders into it cleanly.
    restoreDraft(snapshotRef.current)
    linesRef.current = []
    interimRef.current = ''
    lastSegmentAtRef.current = 0
    lastVoiceAtRef.current = 0
    everVoicedRef.current = false
    onTranscript('')

    void startAudioViz(session)
    void (async () => {
      try {
        const handle = await startTranscription('mic', {
          onLine: (l) => {
            if (sessionRef.current !== session) return
            // Skip segments the backend re-sends from a PRIOR hold (server-side
            // conversation echo), then upsert by id so re-sent/refined segments
            // within THIS hold don't duplicate either.
            if (l.id != null && consumedIdsRef.current.has(l.id)) return
            upsertLine(linesRef.current, l)
            lastSegmentAtRef.current = Date.now()
            onTranscript(assembleTranscript(linesRef.current, interimRef.current))
          },
          onInterim: (t) => {
            if (sessionRef.current !== session) return
            interimRef.current = t
            onTranscript(assembleTranscript(linesRef.current, interimRef.current))
          },
          onBackend: () => {},
          onError: (e) => {
            if (sessionRef.current === session) setError(e.message)
          }
        })
        // Released/superseded before the connection resolved — tear it straight down.
        if (sessionRef.current !== session) {
          try {
            handle.stop()
          } catch {
            /* ignore */
          }
          return
        }
        handleRef.current = handle
      } catch (e) {
        if (sessionRef.current === session) setError((e as Error).message)
      }
    })()
  }

  const finishRecording = (commit: boolean): void => {
    if (!recordingRef.current) return
    recordingRef.current = false
    setRecording(false)

    if (!commit) {
      teardownTranscription() // also stops the audio viz
      return
    }

    // Keep the mic + transcription stream open through finalize: VAD watches for you
    // to stop talking and the backend still needs ~1.8s for the trailing segment.
    const session = sessionRef.current
    finalizingRef.current = true
    setFinalizing(true)
    const releasedAt = Date.now()

    const commitNow = (): void => {
      if (sessionRef.current !== session) return
      clearPoll()
      finalizingRef.current = false
      setFinalizing(false)
      stopAudioViz()
      try {
        handleRef.current?.stop()
      } catch {
        /* ignore */
      }
      handleRef.current = null
      const text = assembleTranscript(linesRef.current, interimRef.current)
      markConsumed()
      linesRef.current = []
      interimRef.current = ''
      sessionRef.current++ // invalidate any still-pending async work from this session
      // The hold-capture gesture completed (even if STT produced nothing, e.g.
      // quota/1008 or silence) — notify before the text-gated send.
      opts.onCaptureEnd?.()
      if (text) onCommit(text)
    }

    const check = (): void => {
      if (sessionRef.current !== session) return
      const now = Date.now()
      const done = shouldFinalize(
        {
          elapsedMs: now - releasedAt,
          everVoiced: everVoicedRef.current,
          silentForMs: now - lastVoiceAtRef.current,
          sinceLastSegmentMs: lastSegmentAtRef.current > 0 ? now - lastSegmentAtRef.current : null
        },
        FINALIZE_CFG
      )
      if (done) {
        commitNow()
        return
      }
      pollTimerRef.current = setTimeout(check, POLL_MS)
    }
    check()
  }

  const onKeyDown = (e: React.KeyboardEvent): boolean => {
    if (!isSpace(e)) return false
    if (recordingRef.current) {
      // Block the auto-repeat spaces from leaking into the (hidden) input.
      e.preventDefault()
      return true
    }
    // Initial press only (ignore OS auto-repeat). Snapshot the pre-space draft and
    // arm the hold timer; let the space type normally so a tap is a real space.
    if (!e.repeat && holdTimerRef.current === null) {
      snapshotRef.current = (e.currentTarget as HTMLTextAreaElement).value ?? ''
      holdTimerRef.current = setTimeout(() => {
        holdTimerRef.current = null
        startRecording()
      }, HOLD_THRESHOLD_MS)
    }
    return false
  }

  const onKeyUp = (e: React.KeyboardEvent): boolean => {
    if (!isSpace(e)) return false
    if (holdTimerRef.current !== null) {
      // Released before the threshold → it was a tap; the space already typed.
      clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
      return false
    }
    if (recordingRef.current) {
      e.preventDefault()
      finishRecording(true)
      return true
    }
    return false
  }

  const cancel = (): void => {
    if (holdTimerRef.current !== null) {
      clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
    }
    if (recordingRef.current) {
      finishRecording(false)
      return
    }
    // Esc during the finalize window: abort, don't send.
    if (finalizingRef.current) teardownTranscription()
  }

  // Window-level hold-Space so push-to-talk works whenever the overlay window is
  // FOCUSED — not only when the textarea has focus. The textarea keeps its own
  // handlers (onKeyDown/onKeyUp); this only acts when focus is NOT in a text
  // field, so the two never double-handle. Latest start/finish/getDraft are read
  // through refs so the once-registered listeners never call a stale closure.
  const startRecordingRef = useRef(startRecording)
  startRecordingRef.current = startRecording
  const finishRecordingRef = useRef(finishRecording)
  finishRecordingRef.current = finishRecording
  const getDraftRef = useRef(opts.getDraft)
  getDraftRef.current = opts.getDraft

  useEffect(() => {
    const inTextField = (): boolean => {
      const ae = document.activeElement
      return !!ae && (ae.tagName === 'TEXTAREA' || ae.tagName === 'INPUT')
    }
    const isSpaceKey = (e: KeyboardEvent): boolean => e.key === ' ' || e.code === 'Space'
    const onDown = (e: KeyboardEvent): void => {
      if (!isSpaceKey(e) || inTextField()) return // the textarea path owns it when focused
      if (recordingRef.current) {
        e.preventDefault() // swallow auto-repeat spaces while recording
        return
      }
      if (!e.repeat && holdTimerRef.current === null) {
        e.preventDefault() // don't let Space scroll or activate a focused control
        snapshotRef.current = getDraftRef.current()
        holdTimerRef.current = setTimeout(() => {
          holdTimerRef.current = null
          startRecordingRef.current()
        }, HOLD_THRESHOLD_MS)
      }
    }
    const onUp = (e: KeyboardEvent): void => {
      if (!isSpaceKey(e) || inTextField()) return
      if (holdTimerRef.current !== null) {
        // Released before the threshold → a tap; nothing to record.
        clearTimeout(holdTimerRef.current)
        holdTimerRef.current = null
        return
      }
      if (recordingRef.current) {
        e.preventDefault()
        finishRecordingRef.current(true)
      }
    }
    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    return () => {
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
    }
  }, [])

  // Tear everything down if the panel unmounts mid-recording/finalize (e.g. Esc reset).
  useEffect(() => {
    return () => {
      if (holdTimerRef.current !== null) clearTimeout(holdTimerRef.current)
      clearPoll()
      stopAudioViz()
      try {
        handleRef.current?.stop()
      } catch {
        /* ignore */
      }
      handleRef.current = null
      sessionRef.current++
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { recording, finalizing, error, analyserRef, onKeyDown, onKeyUp, cancel }
}
