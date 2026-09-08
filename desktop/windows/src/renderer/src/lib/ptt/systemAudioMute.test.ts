// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { applyPttSystemAudio, restoreSystemAudio, systemAudioActionFor } from './systemAudioMute'
import { reduce, initialState, type PttEvent, type PttState } from './machine'
import { setPreferences } from '../preferences'
import type { AudioStats } from './gate'

// PTT system-audio muting (Track 2 A4). The contract these tests lock in:
//   * MUTE fires at capture-START and only when the pttMuteSystemAudio pref
//     resolves true (undefined ⇒ true, the macOS-faithful default).
//   * RESTORE fires on EVERY capture-END path — release, cancel, watchdog/error,
//     unmount — and is NEVER pref-gated. A mute is always undone.
// The "is audio actually playing / did the user already mute it themselves /
// idempotence" half of the contract is enforced inside the native helper
// (src/main/audio/helper/Program.cs), which can't run headlessly — see the PR
// notes for the manual live check.

const mute = vi.fn()
const restore = vi.fn()

beforeEach(() => {
  mute.mockClear()
  restore.mockClear()
  localStorage.clear()
  setPreferences({ pttMuteSystemAudio: undefined })
  ;(window as unknown as { omi: unknown }).omi = {
    muteSystemAudio: mute,
    restoreSystemAudio: restore
  }
})

/** Drive the REAL reducer and record the system-audio calls its effects produce,
 *  so these expectations track the machine rather than a hand-copied effect list. */
function run(events: PttEvent[]): void {
  let state: PttState = initialState
  for (const event of events) {
    const step = reduce(state, event)
    state = step.state
    for (const eff of step.effects) applyPttSystemAudio(eff.kind)
  }
}

const SPEECH: AudioStats = { totalSec: 3, voicedSec: 2, peak: 8000 } // gate → 'ok'
const TOO_SHORT: AudioStats = { totalSec: 0.05, voicedSec: 0, peak: 8000 } // gate → 'too-short'

describe('systemAudioActionFor', () => {
  it('maps capture-start to mute and both capture-end effects to restore', () => {
    expect(systemAudioActionFor('startCapture')).toBe('mute')
    expect(systemAudioActionFor('startDrain')).toBe('restore') // release
    expect(systemAudioActionFor('stopCapture')).toBe('restore') // cancel / watchdog / unmount
  })

  it('ignores every other effect (no mute churn mid-pipeline)', () => {
    for (const kind of [
      'startStream',
      'startVocabulary',
      'stopStream',
      'armWatchdog',
      'sendFinalize',
      'startBatch',
      'abortBatch',
      'commit',
      'showHint',
      'showError',
      'setLiveText',
      'captureEnded'
    ] as const) {
      expect(systemAudioActionFor(kind)).toBeNull()
    }
  })
})

describe('applyPttSystemAudio — the pref gate', () => {
  it('mutes at capture-start by default (pref unset)', () => {
    run([{ type: 'HOLD_START' }])
    expect(mute).toHaveBeenCalledTimes(1)
  })

  it('mutes when the pref is explicitly on', () => {
    setPreferences({ pttMuteSystemAudio: true })
    run([{ type: 'HOLD_START' }])
    expect(mute).toHaveBeenCalledTimes(1)
  })

  it('does NOT mute when the pref is off', () => {
    setPreferences({ pttMuteSystemAudio: false })
    run([{ type: 'HOLD_START' }])
    expect(mute).not.toHaveBeenCalled()
  })

  it('still restores when the pref is off — restore is unconditional', () => {
    setPreferences({ pttMuteSystemAudio: false })
    run([{ type: 'HOLD_START' }, { type: 'CANCEL' }])
    expect(mute).not.toHaveBeenCalled()
    expect(restore).toHaveBeenCalledTimes(1)
  })
})

describe('applyPttSystemAudio — every capture-end path restores', () => {
  it('release → drain → commit (the happy path)', () => {
    run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: SPEECH },
      { type: 'BATCH_OK', transcript: 'hello' }
    ])
    expect(mute).toHaveBeenCalledTimes(1)
    expect(restore).toHaveBeenCalledTimes(1) // at RELEASE, not at BATCH_OK
  })

  it('cancel mid-hold (Esc / focus loss / unmount)', () => {
    run([{ type: 'HOLD_START' }, { type: 'CANCEL' }])
    expect(mute).toHaveBeenCalledTimes(1)
    expect(restore).toHaveBeenCalledTimes(1)
  })

  it('watchdog timeout after release', () => {
    run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: SPEECH },
      { type: 'WATCHDOG' }
    ])
    expect(mute).toHaveBeenCalledTimes(1)
    // Restored at RELEASE, then again by the watchdog TEARDOWN's stopCapture —
    // the second is an idempotent no-op in the helper, never a stranded mute.
    expect(restore.mock.calls.length).toBeGreaterThanOrEqual(1)
  })

  it('batch failure (the error path)', () => {
    run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: SPEECH },
      { type: 'BATCH_FAIL', message: 'network' }
    ])
    expect(mute).toHaveBeenCalledTimes(1)
    expect(restore).toHaveBeenCalledTimes(1)
  })

  it('too-short hold (gate discards the buffer)', () => {
    run([{ type: 'HOLD_START' }, { type: 'RELEASE' }, { type: 'DRAINED', stats: TOO_SHORT }])
    expect(mute).toHaveBeenCalledTimes(1)
    expect(restore).toHaveBeenCalledTimes(1)
  })

  it('never leaves a hold muted — mute is always followed by a restore', () => {
    // Exhaustive over the terminal events reachable from a hold.
    const endings: PttEvent[][] = [
      [{ type: 'CANCEL' }],
      [{ type: 'RELEASE' }, { type: 'DRAINED', stats: TOO_SHORT }],
      [
        { type: 'RELEASE' },
        { type: 'DRAINED', stats: SPEECH },
        { type: 'BATCH_OK', transcript: '' }
      ],
      [
        { type: 'RELEASE' },
        { type: 'DRAINED', stats: SPEECH },
        { type: 'BATCH_FAIL', message: 'boom' }
      ],
      [{ type: 'RELEASE' }, { type: 'DRAINED', stats: SPEECH }, { type: 'WATCHDOG' }]
    ]
    for (const ending of endings) {
      mute.mockClear()
      restore.mockClear()
      run([{ type: 'HOLD_START' }, ...ending])
      expect(mute).toHaveBeenCalledTimes(1)
      expect(restore.mock.calls.length).toBeGreaterThanOrEqual(1)
    }
  })
})

describe('applyPttSystemAudio — no bridge', () => {
  it('no-ops (never throws) when the preload bridge is absent', () => {
    delete (window as unknown as { omi?: unknown }).omi
    expect(() => run([{ type: 'HOLD_START' }, { type: 'CANCEL' }])).not.toThrow()
    expect(() => restoreSystemAudio()).not.toThrow()
  })
})

describe('restoreSystemAudio', () => {
  it('is unconditional and repeatable (the unmount backstop)', () => {
    setPreferences({ pttMuteSystemAudio: false })
    restoreSystemAudio()
    restoreSystemAudio()
    expect(restore).toHaveBeenCalledTimes(2)
  })
})
