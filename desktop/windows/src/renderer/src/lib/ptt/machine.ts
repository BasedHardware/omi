// Pure push-to-talk state machine (no timers, DOM, or audio — fully unit-testable).
// One machine instance per capture; the hook owns timers/transports and feeds
// events in, then interprets the returned effects. Port of the macOS
// PushToTalkManager design: the locally-retained buffer is the foundation, the
// stream is opportunistic decoration, every wait is bounded, and a hold that
// produced nothing exits fast.
//
//   idle → HOLD_START → holding → RELEASE → draining → (gate) →
//     too-short → idle (+hint)          — rapid re-press works immediately
//     silent    → idle                  — never send silence to STT
//     ok        → streamFinalize (stream connected) | batching (not connected)
//   streamFinalize → STREAM_FINAL → commit (short-circuit)
//                  → deadline/dead → batching
//   batching → BATCH_OK → commit | BATCH_FAIL → error strip
//   any non-idle → CANCEL/WATCHDOG → idle (discard, abort in-flight work)
import { type AudioStats, gateDecision } from './gate'
import { TAP_TO_LOCK_MAX_MS, DOUBLE_TAP_WINDOW_MS } from './constants'

export type PttPhase = 'idle' | 'holding' | 'draining' | 'streamFinalize' | 'batching'

export type PttState = {
  phase: PttPhase
  /** The opportunistic stream reached OPEN (and hasn't died). */
  streamConnected: boolean
  /** Finalized stream segment texts, in arrival order. */
  finals: string[]
  /** The buffer cap warning already fired (fires at most once per hold). */
  bufferCapped: boolean
}

export type PttEvent =
  | { type: 'HOLD_START' }
  | { type: 'RELEASE' }
  | { type: 'CANCEL' }
  | { type: 'DRAINED'; stats: AudioStats }
  | { type: 'STREAM_CONNECTED' }
  | { type: 'STREAM_FINAL'; text: string }
  | { type: 'STREAM_DEAD' }
  | { type: 'FINALIZE_DEADLINE' }
  | { type: 'BATCH_OK'; transcript: string }
  | { type: 'BATCH_FAIL'; message: string }
  | { type: 'BUFFER_CAPPED' }
  | { type: 'WATCHDOG' }

export type PttEffect =
  | { kind: 'startCapture' }
  | { kind: 'startStream' }
  /** Kick off best-effort keyword collection at hold-start so the bounded OCR
   *  overlaps the hold and is free by key-up (A2). The transcribe path consumes
   *  the cached result — see startPttKeywordCollection in vocabulary.ts. */
  | { kind: 'startVocabulary' }
  /** Stop appending audio; resolve the full buffer after DRAIN_MS. */
  | { kind: 'startDrain' }
  | { kind: 'stopCapture' }
  | { kind: 'stopStream' }
  /** Arm the post-release pipeline watchdog (WATCHDOG_MS). Emitted at RELEASE —
   *  never during the hold, which is user-bounded and may run for minutes. */
  | { kind: 'armWatchdog' }
  /** Send 'finalize' on the connected stream; arm STREAM_FINALIZE_DEADLINE_MS. */
  | { kind: 'sendFinalize' }
  /** POST the drained buffer to the batch endpoint; arm BATCH_TIMEOUT_MS. */
  | { kind: 'startBatch' }
  /** Abort an in-flight batch POST (cancel/watchdog paths). */
  | { kind: 'abortBatch' }
  /** The capture's final transcript. Empty string ⇒ caller skips sending. */
  | { kind: 'commit'; text: string }
  | { kind: 'showHint'; hint: 'too-short' | 'too-long' | 'dead-mic' }
  | { kind: 'showError'; message: string }
  /** Live transcript for the input box while the capture is in flight. */
  | { kind: 'setLiveText'; text: string }
  /** The hold GESTURE completed — committed, hinted, discarded, or failed (never
   *  emitted on CANCEL). Drives onboarding's voice step. */
  | { kind: 'captureEnded' }

export const initialState: PttState = {
  phase: 'idle',
  streamConnected: false,
  finals: [],
  bufferCapped: false
}

/** Flatten segment texts into the single string we commit: trimmed, joined with
 *  single spaces, whitespace-only fragments dropped ('' for an empty capture). */
export function assembleTranscript(texts: string[]): string {
  return texts
    .map((t) => t.trim())
    .filter(Boolean)
    .join(' ')
    .trim()
}

type Step = { state: PttState; effects: PttEffect[] }
const stay = (state: PttState): Step => ({ state, effects: [] })

/** Everything a discarded capture must tear down. `abortBatch`/`stopStream` are
 *  no-ops in the hook when nothing is in flight. */
const TEARDOWN: PttEffect[] = [
  { kind: 'stopCapture' },
  { kind: 'stopStream' },
  { kind: 'abortBatch' }
]

export function reduce(s: PttState, e: PttEvent): Step {
  switch (e.type) {
    case 'HOLD_START': {
      if (s.phase !== 'idle') return stay(s)
      return {
        state: { ...initialState, phase: 'holding' },
        effects: [
          { kind: 'startCapture' },
          { kind: 'startStream' },
          { kind: 'startVocabulary' },
          { kind: 'setLiveText', text: '' }
        ]
      }
    }

    case 'RELEASE': {
      if (s.phase !== 'holding') return stay(s)
      return {
        state: { ...s, phase: 'draining' },
        effects: [{ kind: 'armWatchdog' }, { kind: 'startDrain' }]
      }
    }

    case 'CANCEL': {
      if (s.phase === 'idle') return stay(s)
      return { state: { ...s, phase: 'idle' }, effects: TEARDOWN }
    }

    case 'DRAINED': {
      if (s.phase !== 'draining') return stay(s)
      const decision = gateDecision(e.stats)
      if (decision === 'too-short' || decision === 'dead-mic') {
        return {
          state: { ...s, phase: 'idle' },
          effects: [
            { kind: 'stopStream' },
            { kind: 'showHint', hint: decision },
            { kind: 'captureEnded' }
          ]
        }
      }
      if (decision === 'silent') {
        // A live room that simply had no speech — discard without ceremony.
        return {
          state: { ...s, phase: 'idle' },
          effects: [{ kind: 'stopStream' }, { kind: 'captureEnded' }]
        }
      }
      if (s.streamConnected) {
        return { state: { ...s, phase: 'streamFinalize' }, effects: [{ kind: 'sendFinalize' }] }
      }
      return {
        state: { ...s, phase: 'batching' },
        effects: [{ kind: 'stopStream' }, { kind: 'startBatch' }]
      }
    }

    case 'STREAM_CONNECTED': {
      if (s.phase !== 'holding' && s.phase !== 'draining') return stay(s)
      return stay({ ...s, streamConnected: true })
    }

    case 'STREAM_FINAL': {
      // Segments only matter while the stream is authoritative-in-waiting; once
      // batching owns the capture (or it's over), late segments are noise.
      if (s.phase !== 'holding' && s.phase !== 'draining' && s.phase !== 'streamFinalize') {
        return stay(s)
      }
      const finals = [...s.finals, e.text]
      const live = assembleTranscript(finals)
      if (s.phase === 'streamFinalize') {
        // Short-circuit: the post-finalize trailing segment landed — commit now.
        return {
          state: { ...s, finals, phase: 'idle' },
          effects: [
            { kind: 'stopStream' },
            { kind: 'setLiveText', text: live },
            { kind: 'commit', text: live },
            { kind: 'captureEnded' }
          ]
        }
      }
      return { state: { ...s, finals }, effects: [{ kind: 'setLiveText', text: live }] }
    }

    case 'STREAM_DEAD': {
      if (s.phase === 'streamFinalize') {
        // The lane we were waiting on died — fall back to batch instantly.
        return {
          state: { ...s, streamConnected: false, phase: 'batching' },
          effects: [{ kind: 'stopStream' }, { kind: 'startBatch' }]
        }
      }
      // Mid-hold death is invisible: the buffer is the foundation, live text just
      // stops updating. Release will go straight to batch.
      return stay({ ...s, streamConnected: false })
    }

    case 'FINALIZE_DEADLINE': {
      if (s.phase !== 'streamFinalize') return stay(s)
      return {
        state: { ...s, phase: 'batching' },
        effects: [{ kind: 'stopStream' }, { kind: 'startBatch' }]
      }
    }

    case 'BATCH_OK': {
      if (s.phase !== 'batching') return stay(s)
      return {
        state: { ...s, phase: 'idle' },
        effects: [{ kind: 'commit', text: e.transcript.trim() }, { kind: 'captureEnded' }]
      }
    }

    case 'BATCH_FAIL': {
      if (s.phase !== 'batching') return stay(s)
      return {
        state: { ...s, phase: 'idle' },
        effects: [{ kind: 'showError', message: e.message }, { kind: 'captureEnded' }]
      }
    }

    case 'BUFFER_CAPPED': {
      if (s.phase !== 'holding' || s.bufferCapped) return stay(s)
      return {
        state: { ...s, bufferCapped: true },
        effects: [{ kind: 'showHint', hint: 'too-long' }]
      }
    }

    case 'WATCHDOG': {
      // A hold is user-bounded — the key is physically down, and the buffer cap
      // provisions 4.5 MINUTES of speech. The watchdog only guards the
      // post-release pipeline (draining/finalize/batching), where a bug could
      // otherwise strand the "Transcribing…" UI.
      if (s.phase === 'idle' || s.phase === 'holding') return stay(s)
      return {
        state: { ...s, phase: 'idle' },
        effects: [
          ...TEARDOWN,
          { kind: 'showError', message: 'Voice input timed out' },
          { kind: 'captureEnded' }
        ]
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Tap-to-lock latch (hands-free PTT) — a SECOND pure reducer, orthogonal to the
// capture pipeline above. Port of macOS PushToTalkManager's tap-to-lock
// (handleShortcutDown/Up): a quick tap opens a short decision window; a second
// quick tap within it latches LOCKED listening (the mic stays open with no key
// held); a tap while locked finalizes. A long hold never enters this path — the
// hook only feeds TAP_RELEASED for a sub-threshold press — so hold-to-talk is
// unchanged. Like the capture machine this owns no clock: the hook measures the
// tap duration + inter-tap gap and passes them in, so every timing edge
// (0.21s tap, 0.39s vs 0.41s second tap) is unit-testable here.

export type LockPhase = 'idle' | 'pendingLock' | 'locked'

export type LockState = { phase: LockPhase }

export const initialLockState: LockState = { phase: 'idle' }

export type LockEvent =
  /** A press was released as a tap; `holdMs` is how long it was down. */
  | { type: 'TAP_RELEASED'; holdMs: number; doubleTapForLock: boolean }
  /** A new press went down; `gapMs` is the time since the last tap-up. */
  | { type: 'PRESS_DOWN'; gapMs: number }
  /** The pending-lock decision window elapsed with no second tap. */
  | { type: 'WINDOW_EXPIRED' }
  /** Esc / focus loss / unmount. */
  | { type: 'CANCEL' }

export type LockEffect =
  /** Arm the decision window (DOUBLE_TAP_WINDOW_MS) → WINDOW_EXPIRED on elapse. */
  | { kind: 'armWindow' }
  /** Drop the decision window. */
  | { kind: 'cancelWindow' }
  /** Latch locked — the hook starts a hands-free capture (a normal hold that is
   *  not tied to a key-up). */
  | { kind: 'enterLocked' }
  /** End the locked capture — the hook releases it into the transcribe pipeline. */
  | { kind: 'finalizeLocked' }

export type LockStep = { state: LockState; effects: LockEffect[] }

const lockStay = (state: LockState): LockStep => ({ state, effects: [] })

export function reduceLock(s: LockState, e: LockEvent): LockStep {
  switch (e.type) {
    case 'TAP_RELEASED': {
      // Only a fast tap while the setting is on opens the window; a slower tap is
      // an ordinary tap and never latches.
      if (s.phase === 'idle' && e.doubleTapForLock && e.holdMs < TAP_TO_LOCK_MAX_MS) {
        return { state: { phase: 'pendingLock' }, effects: [{ kind: 'armWindow' }] }
      }
      return lockStay(s)
    }
    case 'PRESS_DOWN': {
      if (s.phase === 'pendingLock') {
        // Second tap inside the window → latch locked; too late → fall back to idle
        // (the hook treats this press as a fresh gesture).
        if (e.gapMs < DOUBLE_TAP_WINDOW_MS) {
          return {
            state: { phase: 'locked' },
            effects: [{ kind: 'cancelWindow' }, { kind: 'enterLocked' }]
          }
        }
        return { state: { phase: 'idle' }, effects: [{ kind: 'cancelWindow' }] }
      }
      if (s.phase === 'locked') {
        return { state: { phase: 'idle' }, effects: [{ kind: 'finalizeLocked' }] }
      }
      return lockStay(s)
    }
    case 'WINDOW_EXPIRED': {
      if (s.phase === 'pendingLock') return { state: { phase: 'idle' }, effects: [] }
      return lockStay(s)
    }
    case 'CANCEL': {
      if (s.phase === 'idle') return lockStay(s)
      // Discarding the locked capture is the hook's job (it cancels the active
      // capture); here we only drop the latch + any pending window.
      const effects: LockEffect[] = s.phase === 'pendingLock' ? [{ kind: 'cancelWindow' }] : []
      return { state: { phase: 'idle' }, effects }
    }
  }
}
