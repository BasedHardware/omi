import { useEffect, useRef, useState } from 'react'
import { reduce, initialState, type PttEvent, type PttState } from '../lib/ptt/machine'
import { voicedStats } from '../lib/ptt/gate'
import {
  startPttCapture,
  warmPttMic,
  releasePttMic,
  rebuildPttMic,
  type PttCapture
} from '../lib/ptt/capture'
import { DeadMicPolicy, applyDeadMicTurn } from '../lib/ptt/deadMicPolicy'
import {
  startPttStream,
  batchTranscribe,
  batchErrorMessage,
  prefetchAuthToken,
  type PttStream
} from '../lib/ptt/transport'
import { startPttKeywordCollection } from '../lib/ptt/vocabulary'
import {
  HOLD_THRESHOLD_MS,
  STREAM_FINALIZE_DEADLINE_MS,
  HINT_MS,
  TOO_LONG_HINT_MS,
  ERROR_STRIP_MS,
  WATCHDOG_MS,
  MIC_IDLE_RELEASE_MS,
  MIC_TAP_RELEASE_MS,
  RECORDING_TOO_LONG_MESSAGE
} from '../lib/ptt/constants'
import { PCM_PENDING_MAX_BYTES, type WaveformSource } from '../../../shared/types'

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
  /** Fires at the start of every new PTT hold (once the hold threshold is
   *  crossed and capture begins) — the barge-in seam. macOS calls
   *  FloatingBarVoicePlaybackService.interruptCurrentResponse() at exactly this
   *  point so a new hold cuts off Omi's still-playing spoken reply. */
  onHoldStart?: () => void
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
  /** Live amplitude source for the waveform (null while not capturing). Structural
   *  WaveformSource — a real AnalyserNode or the IPC-fed PTT adapter both satisfy it. */
  analyserRef: React.MutableRefObject<WaveformSource | null>
  /** Wire to the input's onKeyDown. True = consumed (skip Enter/typing handling). */
  onKeyDown: (e: React.KeyboardEvent) => boolean
  /** Wire to the input's onKeyUp. True = consumed. */
  onKeyUp: (e: React.KeyboardEvent) => boolean
  /** Programmatic gesture entry points for main-process-driven holds (the bar's
   *  summon-hotkey hold). Semantically identical to Space key-down/key-up: the
   *  hook's own threshold timer still decides tap vs hold, the warm mic
   *  backfills from beginHold, and a sub-threshold begin→end pair is a no-op. */
  beginHold: () => void
  endHold: () => void
  /** Abort the active capture without sending (Esc / focus loss / unmount). */
  cancel: () => void
}

const HINTS = {
  'too-short': { text: 'Hold longer to record', ms: HINT_MS },
  'too-long': { text: RECORDING_TOO_LONG_MESSAGE, ms: TOO_LONG_HINT_MS },
  'dead-mic': {
    text: 'Mic heard nothing — check your input device in Windows sound settings',
    ms: TOO_LONG_HINT_MS
  },
  // Escalated after repeated dead-mic turns (silent-mic recovery, A7b): the
  // automatic capture-stack rebuild didn't help, so prompt a stronger action.
  'dead-mic-escalated': {
    text: 'Mic still silent — check your microphone, or restart Omi',
    ms: TOO_LONG_HINT_MS
  }
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
  /** Chunks produced before the stream session resolved (incl. the key-down
   *  backfill) — flushed into the stream in order the moment it exists, so the
   *  stream lane hears the same audio the batch buffer holds. Bounded. */
  pendingStream: Int16Array[]
  pendingStreamBytes: number
  buffer: Int16Array | null
  abort: AbortController | null
  deadlineTimer: ReturnType<typeof setTimeout> | null
  watchdogTimer: ReturnType<typeof setTimeout> | null
  /** Time between the physical key-down and the hold threshold firing — the
   *  warm mic backfills this much pre-roll so the threshold costs no speech. */
  backfillMs: number
}

function isSpace(e: { key: string; code: string }): boolean {
  return e.key === ' ' || e.code === 'Space'
}

export function usePushToTalk(opts: Options): PushToTalk {
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [hint, setHint] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const analyserRef = useRef<WaveformSource | null>(null)

  // The ACTIVE (foreground) job — the one bound to UI state. Superseded jobs run
  // headless until they finish.
  const jobRef = useRef<Job | null>(null)
  // Every job still in flight (foreground + background) — so unmount can cancel
  // background captures too, not just the active one.
  const liveJobsRef = useRef(new Set<Job>())
  // Pending hold timer (armed at key-down; firing starts the capture).
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // When the physical key went down — the warm mic backfills from this moment.
  const keyDownAtRef = useRef(0)
  // Draft snapshot taken at key-down, restored when the hold crosses the threshold.
  const snapshotRef = useRef('')
  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Warm-mic idle linger: the graph opens at Space key-down and closes after a
  // Space-inactivity window (short after a mere tap, long after PTT use) — or on
  // overlay blur/hide.
  const micIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Consecutive dead-mic turns across holds (macOS PTTSilentMicRecoveryPolicy):
  // drives the capture-rebuild-then-escalate ladder. Persists across holds.
  const deadMicPolicyRef = useRef(new DeadMicPolicy())

  const optsRef = useRef(opts)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref (once-registered listeners read the newest callbacks)
  optsRef.current = opts

  const isForeground = (job: Job): boolean => jobRef.current === job
  /** Synchronous "is a hold capturing right now" for the key handlers — derived
   *  from the machine state, never a second source of truth. */
  const isHolding = (): boolean => jobRef.current?.state.phase === 'holding'

  // Acquire the mic NOW (macOS parity: capture starts at key-down, not at the
  // hold threshold), prefetch the auth token alongside the mic spin-up, and
  // (re-)arm the idle release. If the timer fires mid-capture, releasePttMic
  // defers internally until the capture detaches.
  const armMicIdleRelease = (ms: number): void => {
    if (micIdleTimerRef.current) clearTimeout(micIdleTimerRef.current)
    micIdleTimerRef.current = setTimeout(() => releasePttMic(), ms)
  }
  const touchMic = (): void => {
    void warmPttMic()
    prefetchAuthToken()
    armMicIdleRelease(MIC_IDLE_RELEASE_MS)
  }

  const showHint = (which: keyof typeof HINTS): void => {
    setHint(HINTS[which].text)
    if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
    hintTimerRef.current = setTimeout(() => setHint(null), HINTS[which].ms)
  }
  const showError = (message: string): void => {
    setError(message)
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
    errorTimerRef.current = setTimeout(() => setError(null), ERROR_STRIP_MS)
  }

  const syncUi = (job: Job): void => {
    if (!isForeground(job)) return
    const { phase } = job.state
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

    // Whether THIS step's terminal turn was classed dead-mic — the dead-mic hint's
    // display is deferred to captureEnded so the silent-mic policy can pick base vs
    // escalated text (showHint and captureEnded arrive in the same effects batch).
    let deadMicTurn = false

    for (const eff of effects) {
      switch (eff.kind) {
        case 'startCapture': {
          job.capturePromise = startPttCapture({
            onChunk: (pcm) => {
              // Until the stream session exists, queue (bounded) so the stream
              // lane hears the backfill + early speech too — otherwise the fast
              // short-circuit commit would be missing the opening words.
              if (job.stream) {
                job.stream.feed(pcm)
              } else if (!job.streamStopped) {
                job.pendingStream.push(pcm)
                job.pendingStreamBytes += pcm.byteLength
                while (
                  job.pendingStreamBytes > PCM_PENDING_MAX_BYTES &&
                  job.pendingStream.length > 1
                ) {
                  job.pendingStreamBytes -= job.pendingStream.shift()!.byteLength
                }
              }
            },
            onCapped: () => dispatch(job, { type: 'BUFFER_CAPPED' }),
            backfillMs: job.backfillMs
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
        case 'startVocabulary': {
          // Overlap keyword collection with the hold so its bounded OCR is free
          // by key-up; batchTranscribe consumes the cached result. Best-effort —
          // startPttKeywordCollection never throws.
          startPttKeywordCollection()
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
              // Flush the audio captured while the session was being created
              // (backfill + early speech), in order, then go live.
              for (const pcm of job.pendingStream) stream.feed(pcm)
              job.pendingStream = []
              job.pendingStreamBytes = 0
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
          job.pendingStream = []
          job.pendingStreamBytes = 0
          break
        }
        case 'armWatchdog': {
          job.watchdogTimer = setTimeout(() => dispatch(job, { type: 'WATCHDOG' }), WATCHDOG_MS)
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
              const transcript = await batchTranscribe(
                job.buffer ?? new Int16Array(0),
                abort.signal
              )
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
          // Defer the dead-mic hint to the policy step (base vs escalated); show
          // the other hints (too-short / too-long) immediately.
          if (eff.hint === 'dead-mic') {
            deadMicTurn = true
            break
          }
          if (isForeground(job)) showHint(eff.hint)
          break
        }
        case 'showError': {
          if (isForeground(job)) showError(eff.message)
          else console.warn('[ptt] background capture failed:', eff.message)
          break
        }
        case 'captureEnded': {
          optsRef.current.onCaptureEnd?.()
          // Silent-mic escalation (A7b, macOS PTTSilentMicRecoveryPolicy): count
          // consecutive dead-mic turns — rebuild the capture stack at 2, escalate
          // the hint + emit distinct telemetry at 3. A non-dead turn resets. Only
          // the foreground turn drives UI + recovery.
          if (isForeground(job)) {
            applyDeadMicTurn(deadMicPolicyRef.current, deadMicTurn, {
              rebuild: rebuildPttMic,
              showHint
            })
          }
          break
        }
      }
    }

    if (job.state.phase === 'idle' && prevPhase !== 'idle') {
      clearJobTimers(job)
      liveJobsRef.current.delete(job)
      // Release the big audio references immediately — the finished job object
      // lives on in jobRef until the next hold, and the buffer (plus the capture
      // closure's chunk array via capturePromise) is up to ~17MB.
      job.buffer = null
      job.capturePromise = null
      job.pendingStream = []
      job.pendingStreamBytes = 0
    }
    syncUi(job)
  }

  const startHold = (): void => {
    // Barge-in: a new hold interrupts Omi's still-playing spoken reply at
    // hold-start (macOS PushToTalkManager.startListening → interruptCurrentResponse),
    // before mic capture begins. Safe no-op when nothing is playing.
    optsRef.current.onHoldStart?.()
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
      pendingStream: [],
      pendingStreamBytes: 0,
      buffer: null,
      abort: null,
      deadlineTimer: null,
      watchdogTimer: null,
      backfillMs: keyDownAtRef.current > 0 ? Date.now() - keyDownAtRef.current : 0
    }
    jobRef.current = job
    liveJobsRef.current.add(job)
    setError(null)
    setHint(null)
    // Take back the space(s) auto-repeat typed while holding, then clear the box
    // so the live transcript renders cleanly.
    optsRef.current.restoreDraft(snapshotRef.current)
    dispatch(job, { type: 'HOLD_START' })
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

  // --- Space gesture (tap types a space; a ≥350ms hold records) ----------------
  // One implementation shared by the textarea handlers and the window-level
  // listeners; the wrappers differ only in snapshot source and preventDefault.

  /** Key-down: warm the mic, snapshot the draft, arm the threshold timer. */
  const gestureDown = (snapshot: string): void => {
    keyDownAtRef.current = Date.now()
    touchMic()
    snapshotRef.current = snapshot
    holdTimerRef.current = setTimeout(() => {
      holdTimerRef.current = null
      startHold()
    }, HOLD_THRESHOLD_MS)
  }

  /** Key-up: resolve the gesture. 'tap' = threshold not reached (the space
   *  types); 'released' = a hold ended (consumed); 'none' = not ours. */
  const gestureUp = (): 'tap' | 'released' | 'none' => {
    if (holdTimerRef.current !== null) {
      clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
      // A mere typed space: don't keep the mic open the whole time the user is
      // typing a sentence — shorten the linger to a quick-re-press window.
      armMicIdleRelease(MIC_TAP_RELEASE_MS)
      return 'tap'
    }
    const job = jobRef.current
    if (job && job.state.phase === 'holding') {
      dispatch(job, { type: 'RELEASE' })
      return 'released'
    }
    return 'none'
  }

  /** Main-process-driven hold (bar hotkey): same path as a physical Space
   *  key-down/key-up on the window. */
  const beginHold = (): void => {
    if (isHolding() || holdTimerRef.current !== null) return
    gestureDown(optsRef.current.getDraft())
  }
  const endHold = (): void => {
    gestureUp()
  }

  const onKeyDown = (e: React.KeyboardEvent): boolean => {
    if (!isSpace(e)) return false
    if (isHolding()) {
      e.preventDefault() // swallow auto-repeat spaces while recording
      return true
    }
    if (!e.repeat && holdTimerRef.current === null) {
      gestureDown((e.currentTarget as HTMLTextAreaElement).value ?? '')
    }
    return false
  }

  const onKeyUp = (e: React.KeyboardEvent): boolean => {
    if (!isSpace(e)) return false
    if (gestureUp() === 'released') {
      e.preventDefault()
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
      if (isHolding()) {
        e.preventDefault()
        return
      }
      if (!e.repeat && holdTimerRef.current === null) {
        e.preventDefault() // don't let Space scroll or activate a focused control
        gestureDown(optsRef.current.getDraft())
      }
    }
    const onUp = (e: KeyboardEvent): void => {
      if (!isSpace(e) || inTextField()) return
      if (gestureUp() === 'released') e.preventDefault()
    }
    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    return () => {
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- gestureDown/Up are stable via refs
  }, [])

  // Privacy backstop: the moment the overlay hides or loses focus, any lingering
  // warm mic is released (the hook is the single owner of mic lifecycle policy).
  // Guarded — the bridge doesn't exist under jsdom tests.
  useEffect(() => {
    const bridge = (window as { omiOverlay?: typeof window.omiOverlay }).omiOverlay
    if (!bridge) return
    const unActive = bridge.onActiveChange((active) => {
      if (!active) releasePttMic()
    })
    const unHide = bridge.onWillHide(() => releasePttMic())
    return () => {
      unActive()
      unHide()
    }
  }, [])

  // Tear down on unmount: cancel every in-flight job (foreground and superseded
  // background ones — so no timer or transport callback fires into an unmounted
  // tree), clear timers, drop the mic.
  useEffect(() => {
    return () => {
      if (holdTimerRef.current !== null) clearTimeout(holdTimerRef.current)
      if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
      if (micIdleTimerRef.current) clearTimeout(micIdleTimerRef.current)
      for (const job of [...liveJobsRef.current]) {
        if (job.state.phase !== 'idle') dispatch(job, { type: 'CANCEL' })
      }
      releasePttMic()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    recording,
    transcribing,
    hint,
    error,
    analyserRef,
    onKeyDown,
    onKeyUp,
    beginHold,
    endHold,
    cancel
  }
}
