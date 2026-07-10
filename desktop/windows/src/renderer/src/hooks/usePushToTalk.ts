import { useEffect, useRef, useState } from 'react'
import { reduce, initialState, type PttEvent, type PttState } from '../lib/ptt/machine'
import { voicedStats } from '../lib/ptt/gate'
import { startPttCapture, type PttCapture } from '../lib/ptt/capture'
import { startPttStream, batchTranscribe, batchErrorMessage, type PttStream } from '../lib/ptt/transport'
import {
  HOLD_THRESHOLD_MS,
  STREAM_FINALIZE_DEADLINE_MS,
  HINT_MS,
  TOO_LONG_HINT_MS,
  ERROR_STRIP_MS,
  WATCHDOG_MS
} from '../lib/ptt/constants'

// Hold-Space push-to-talk, buffer-first (macOS architecture): one mic capture per
// hold feeds a local PCM buffer + the waveform + an opportunistic live stream. On
// release, local gates decide instantly (hint / silent discard / transcribe); a
// connected stream gets 3s to deliver the finalized transcript, otherwise the
// buffer is batch-POSTed. The pure state machine lives in lib/ptt/machine.ts —
// this hook only owns timers, transports, and React state.

type Options = {
  /** Final transcript on hold-release (non-empty only) — caller auto-sends it. */
  onCommit: (text: string) => void
  /** Live transcript while capturing (stream lane finals). Fires '' at the start
   *  of a capture and after the ACTIVE capture commits, so leftovers never linger.
   *  A superseded background capture never touches the draft. */
  onTranscript: (text: string) => void
  /** Fires when a hold-capture completes (committed, empty, hinted, or failed —
   *  not cancelled), so onboarding can treat the GESTURE as done even without a
   *  transcript. */
  onCaptureEnd?: () => void
  /** Restore the input to its pre-hold contents (removes the held-Space spaces). */
  restoreDraft: (snapshot: string) => void
  /** Current draft, read at key-down on the window-level (unfocused) hold path. */
  getDraft: () => string
}

export type PushToTalk = {
  /** True while Space is held and the mic is capturing. */
  recording: boolean
  /** True after release while the transcript is being finalized (stream or batch). */
  transcribing: boolean
  /** Friendly guidance ("Hold longer to record") — auto-clears. */
  hint: string | null
  /** Failure strip message — auto-clears. */
  error: string | null
  /** Live analyser for the waveform (null while not capturing). */
  analyserRef: React.MutableRefObject<AnalyserNode | null>
  /** Wire to the input's onKeyDown. True = consumed (skip Enter/typing handling). */
  onKeyDown: (e: React.KeyboardEvent) => boolean
  /** Wire to the input's onKeyUp. True = consumed. */
  onKeyUp: (e: React.KeyboardEvent) => boolean
  /** Abort the active capture without sending (Esc / focus loss / unmount). */
  cancel: () => void
}

const HINT_TEXT = {
  'too-short': 'Hold longer to record',
  'too-long': 'Recording too long — keep it under 5 minutes'
} as const

/** One capture's mutable world: its machine state plus everything the effects
 *  operate on. A new hold creates a fresh job; a prior job still transcribing
 *  keeps running in the background and commits (or fails) on its own. */
type Job = {
  state: PttState
  capture: PttCapture | null
  capturePromise: Promise<PttCapture | null> | null
  stream: PttStream | null
  streamStopped: boolean
  buffer: Int16Array | null
  abort: AbortController | null
  deadlineTimer: ReturnType<typeof setTimeout> | null
  watchdogTimer: ReturnType<typeof setTimeout> | null
}

function isSpace(e: { key: string; code: string }): boolean {
  return e.key === ' ' || e.code === 'Space'
}

export function usePushToTalk(opts: Options): PushToTalk {
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [hint, setHint] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)

  // The ACTIVE (foreground) job — the one bound to UI state. Superseded jobs run
  // headless until they finish.
  const jobRef = useRef<Job | null>(null)
  // Mirrors the active job's phase for synchronous reads in key handlers.
  const recordingRef = useRef(false)
  // Pending hold timer (armed at key-down; firing starts the capture).
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Draft snapshot taken at key-down, restored when the hold crosses the threshold.
  const snapshotRef = useRef('')
  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const optsRef = useRef(opts)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref (once-registered listeners read the newest callbacks)
  optsRef.current = opts

  const isForeground = (job: Job): boolean => jobRef.current === job

  const showHint = (text: string, ms: number): void => {
    setHint(text)
    if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
    hintTimerRef.current = setTimeout(() => setHint(null), ms)
  }
  const showError = (message: string): void => {
    setError(message)
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
    errorTimerRef.current = setTimeout(() => setError(null), ERROR_STRIP_MS)
  }

  const syncUi = (job: Job): void => {
    if (!isForeground(job)) return
    const { phase } = job.state
    recordingRef.current = phase === 'holding'
    setRecording(phase === 'holding')
    setTranscribing(phase === 'draining' || phase === 'streamFinalize' || phase === 'batching')
  }

  const clearJobTimers = (job: Job): void => {
    if (job.deadlineTimer) clearTimeout(job.deadlineTimer)
    if (job.watchdogTimer) clearTimeout(job.watchdogTimer)
    job.deadlineTimer = null
    job.watchdogTimer = null
  }

  const dispatch = (job: Job, event: PttEvent): void => {
    const prevPhase = job.state.phase
    const { state, effects } = reduce(job.state, event)
    job.state = state

    for (const eff of effects) {
      switch (eff.kind) {
        case 'startCapture': {
          job.capturePromise = startPttCapture({
            onChunk: (pcm) => job.stream?.feed(pcm),
            onCapped: () => dispatch(job, { type: 'BUFFER_CAPPED' })
          })
            .then((capture) => {
              if (job.state.phase === 'idle') {
                capture.dispose()
                return null
              }
              job.capture = capture
              if (isForeground(job)) analyserRef.current = capture.analyser
              return capture
            })
            .catch((err: Error) => {
              console.warn('[ptt] mic capture failed:', err.message)
              if (isForeground(job)) showError('Microphone unavailable')
              dispatch(job, { type: 'CANCEL' })
              return null
            })
          break
        }
        case 'startStream': {
          startPttStream({
            onConnected: () => dispatch(job, { type: 'STREAM_CONNECTED' }),
            onFinal: (text) => dispatch(job, { type: 'STREAM_FINAL', text }),
            onDead: () => dispatch(job, { type: 'STREAM_DEAD' })
          })
            .then((stream) => {
              if (job.streamStopped || job.state.phase === 'idle') {
                stream.stop()
                return
              }
              job.stream = stream
            })
            .catch(() => dispatch(job, { type: 'STREAM_DEAD' }))
          break
        }
        case 'startDrain': {
          void (async () => {
            const capture = await job.capturePromise
            if (!capture) return // mic failure already cancelled the job
            const buffer = await capture.drain()
            job.capture = null
            if (isForeground(job)) analyserRef.current = null
            job.buffer = buffer
            dispatch(job, { type: 'DRAINED', stats: voicedStats(buffer) })
          })()
          break
        }
        case 'stopCapture': {
          job.capture?.dispose()
          job.capture = null
          if (isForeground(job)) analyserRef.current = null
          break
        }
        case 'stopStream': {
          job.streamStopped = true
          job.stream?.stop()
          job.stream = null
          break
        }
        case 'sendFinalize': {
          job.stream?.finalize()
          job.deadlineTimer = setTimeout(
            () => dispatch(job, { type: 'FINALIZE_DEADLINE' }),
            STREAM_FINALIZE_DEADLINE_MS
          )
          break
        }
        case 'startBatch': {
          const abort = new AbortController()
          job.abort = abort
          void (async () => {
            try {
              const transcript = await batchTranscribe(job.buffer ?? new Int16Array(0), abort.signal)
              dispatch(job, { type: 'BATCH_OK', transcript })
            } catch (err) {
              if (abort.signal.aborted) return // cancelled — the job is already idle
              dispatch(job, { type: 'BATCH_FAIL', message: batchErrorMessage(err) })
            }
          })()
          break
        }
        case 'abortBatch': {
          job.abort?.abort()
          job.abort = null
          break
        }
        case 'commit': {
          if (isForeground(job)) optsRef.current.onTranscript('')
          if (eff.text) optsRef.current.onCommit(eff.text)
          break
        }
        case 'setLiveText': {
          if (isForeground(job)) optsRef.current.onTranscript(eff.text)
          break
        }
        case 'showHint': {
          if (isForeground(job)) {
            showHint(HINT_TEXT[eff.hint], eff.hint === 'too-long' ? TOO_LONG_HINT_MS : HINT_MS)
          }
          break
        }
        case 'showError': {
          if (isForeground(job)) showError(eff.message)
          else console.warn('[ptt] background capture failed:', eff.message)
          break
        }
      }
    }

    if (job.state.phase === 'idle' && prevPhase !== 'idle') {
      clearJobTimers(job)
      // The gesture completed (committed / hinted / silent / failed) — cancel is
      // the one exit that isn't a completed gesture. Holding→idle only happens on
      // cancel/watchdog, so a threshold-crossed-but-aborted hold doesn't count.
      if (event.type !== 'CANCEL' && prevPhase !== 'holding') {
        optsRef.current.onCaptureEnd?.()
      }
    }
    syncUi(job)
  }

  const startHold = (): void => {
    // A prior job still pre-release can't coexist with a new hold (only possible
    // via focus glitches); one already transcribing keeps running in the
    // background and commits on its own — the new hold never kills it.
    const prev = jobRef.current
    if (prev && (prev.state.phase === 'holding' || prev.state.phase === 'draining')) {
      dispatch(prev, { type: 'CANCEL' })
    }
    const job: Job = {
      state: initialState,
      capture: null,
      capturePromise: null,
      stream: null,
      streamStopped: false,
      buffer: null,
      abort: null,
      deadlineTimer: null,
      watchdogTimer: null
    }
    jobRef.current = job
    setError(null)
    setHint(null)
    // Take back the space(s) auto-repeat typed while holding, then clear the box
    // so the live transcript renders cleanly.
    optsRef.current.restoreDraft(snapshotRef.current)
    job.watchdogTimer = setTimeout(() => dispatch(job, { type: 'WATCHDOG' }), WATCHDOG_MS)
    dispatch(job, { type: 'HOLD_START' })
  }

  const release = (): void => {
    const job = jobRef.current
    if (job && job.state.phase === 'holding') dispatch(job, { type: 'RELEASE' })
  }

  const cancel = (): void => {
    if (holdTimerRef.current !== null) {
      clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
    }
    const job = jobRef.current
    if (job && job.state.phase !== 'idle') dispatch(job, { type: 'CANCEL' })
    setHint(null)
  }

  // --- Space gesture wiring (tap types a space; a ≥350ms hold records) ---------

  const onKeyDown = (e: React.KeyboardEvent): boolean => {
    if (!isSpace(e)) return false
    if (recordingRef.current) {
      e.preventDefault() // swallow auto-repeat spaces while recording
      return true
    }
    if (!e.repeat && holdTimerRef.current === null) {
      snapshotRef.current = (e.currentTarget as HTMLTextAreaElement).value ?? ''
      holdTimerRef.current = setTimeout(() => {
        holdTimerRef.current = null
        startHold()
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
      release()
      return true
    }
    return false
  }

  // Window-level hold-Space so PTT works whenever the overlay window is FOCUSED —
  // not only when the textarea has focus. The textarea keeps its own handlers;
  // this path only acts when focus is NOT in a text field, so they never
  // double-handle.
  useEffect(() => {
    const inTextField = (): boolean => {
      const ae = document.activeElement
      return !!ae && (ae.tagName === 'TEXTAREA' || ae.tagName === 'INPUT')
    }
    const onDown = (e: KeyboardEvent): void => {
      if (!isSpace(e) || inTextField()) return
      if (recordingRef.current) {
        e.preventDefault()
        return
      }
      if (!e.repeat && holdTimerRef.current === null) {
        e.preventDefault() // don't let Space scroll or activate a focused control
        snapshotRef.current = optsRef.current.getDraft()
        holdTimerRef.current = setTimeout(() => {
          holdTimerRef.current = null
          startHold()
        }, HOLD_THRESHOLD_MS)
      }
    }
    const onUp = (e: KeyboardEvent): void => {
      if (!isSpace(e) || inTextField()) return
      if (holdTimerRef.current !== null) {
        clearTimeout(holdTimerRef.current)
        holdTimerRef.current = null
        return
      }
      if (recordingRef.current) {
        e.preventDefault()
        release()
      }
    }
    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    return () => {
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- startHold/release are stable via refs
  }, [])

  // Tear down on unmount: cancel the active capture and clear UI timers.
  useEffect(() => {
    return () => {
      if (holdTimerRef.current !== null) clearTimeout(holdTimerRef.current)
      if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
      const job = jobRef.current
      if (job && job.state.phase !== 'idle') dispatch(job, { type: 'CANCEL' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { recording, transcribing, hint, error, analyserRef, onKeyDown, onKeyUp, cancel }
}
