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
  /** Stop appending audio; resolve the full buffer after DRAIN_MS. */
  | { kind: 'startDrain' }
  | { kind: 'stopCapture' }
  | { kind: 'stopStream' }
  /** Send 'finalize' on the connected stream; arm STREAM_FINALIZE_DEADLINE_MS. */
  | { kind: 'sendFinalize' }
  /** POST the drained buffer to the batch endpoint; arm BATCH_TIMEOUT_MS. */
  | { kind: 'startBatch' }
  /** Abort an in-flight batch POST (cancel/watchdog paths). */
  | { kind: 'abortBatch' }
  /** The capture's final transcript. Empty string ⇒ caller skips sending. */
  | { kind: 'commit'; text: string }
  | { kind: 'showHint'; hint: 'too-short' | 'too-long' }
  | { kind: 'showError'; message: string }
  /** Live transcript for the input box while the capture is in flight. */
  | { kind: 'setLiveText'; text: string }

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
const TEARDOWN: PttEffect[] = [{ kind: 'stopCapture' }, { kind: 'stopStream' }, { kind: 'abortBatch' }]

export function reduce(s: PttState, e: PttEvent): Step {
  switch (e.type) {
    case 'HOLD_START': {
      if (s.phase !== 'idle') return stay(s)
      return {
        state: { ...initialState, phase: 'holding' },
        effects: [{ kind: 'startCapture' }, { kind: 'startStream' }, { kind: 'setLiveText', text: '' }]
      }
    }

    case 'RELEASE': {
      if (s.phase !== 'holding') return stay(s)
      return { state: { ...s, phase: 'draining' }, effects: [{ kind: 'startDrain' }] }
    }

    case 'CANCEL': {
      if (s.phase === 'idle') return stay(s)
      return { state: { ...s, phase: 'idle' }, effects: TEARDOWN }
    }

    case 'DRAINED': {
      if (s.phase !== 'draining') return stay(s)
      const decision = gateDecision(e.stats)
      if (decision === 'too-short') {
        return {
          state: { ...s, phase: 'idle' },
          effects: [{ kind: 'stopStream' }, { kind: 'showHint', hint: 'too-short' }]
        }
      }
      if (decision === 'silent') {
        return { state: { ...s, phase: 'idle' }, effects: [{ kind: 'stopStream' }] }
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
          effects: [{ kind: 'stopStream' }, { kind: 'setLiveText', text: live }, { kind: 'commit', text: live }]
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
      return { state: { ...s, phase: 'idle' }, effects: [{ kind: 'commit', text: e.transcript.trim() }] }
    }

    case 'BATCH_FAIL': {
      if (s.phase !== 'batching') return stay(s)
      return { state: { ...s, phase: 'idle' }, effects: [{ kind: 'showError', message: e.message }] }
    }

    case 'BUFFER_CAPPED': {
      if (s.phase !== 'holding' || s.bufferCapped) return stay(s)
      return {
        state: { ...s, bufferCapped: true },
        effects: [{ kind: 'showHint', hint: 'too-long' }]
      }
    }

    case 'WATCHDOG': {
      if (s.phase === 'idle') return stay(s)
      return {
        state: { ...s, phase: 'idle' },
        effects: [...TEARDOWN, { kind: 'showError', message: 'Voice input timed out' }]
      }
    }
  }
}
