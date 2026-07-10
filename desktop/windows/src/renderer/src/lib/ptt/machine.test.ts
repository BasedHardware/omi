import { describe, it, expect } from 'vitest'
import { reduce, initialState, assembleTranscript, type PttEvent, type PttState, type PttEffect } from './machine'

// Gate-passing stats (total ≥ 0.35s, voiced ≥ 0.2s) and the two failing shapes.
const OK_STATS = { totalSec: 2.0, voicedSec: 1.5 }
const SHORT_STATS = { totalSec: 0.2, voicedSec: 0.2 }
const SILENT_STATS = { totalSec: 2.0, voicedSec: 0.05 }

/** Fold events from idle, returning the final state and ALL effects in order. */
function run(events: PttEvent[], from: PttState = initialState): { state: PttState; effects: PttEffect[] } {
  let state = from
  const effects: PttEffect[] = []
  for (const e of events) {
    const step = reduce(state, e)
    state = step.state
    effects.push(...step.effects)
  }
  return { state, effects }
}

const kinds = (effects: PttEffect[]): string[] => effects.map((e) => e.kind)
const commitOf = (effects: PttEffect[]): string | null => {
  const c = effects.find((e) => e.kind === 'commit')
  return c && c.kind === 'commit' ? c.text : null
}

describe('happy paths', () => {
  it('stream short-circuit: hold → connect → release → finalize → segment commits instantly', () => {
    const { state, effects } = run([
      { type: 'HOLD_START' },
      { type: 'STREAM_CONNECTED' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: OK_STATS },
      { type: 'STREAM_FINAL', text: 'hello world' }
    ])
    expect(state.phase).toBe('idle')
    expect(commitOf(effects)).toBe('hello world')
    expect(kinds(effects)).toContain('sendFinalize')
    expect(kinds(effects)).not.toContain('startBatch')
  })

  it('release-before-connect goes straight to batch — sendFinalize is never emitted', () => {
    const { state, effects } = run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: OK_STATS },
      { type: 'BATCH_OK', transcript: '  hello from batch  ' }
    ])
    expect(state.phase).toBe('idle')
    expect(kinds(effects)).not.toContain('sendFinalize')
    expect(kinds(effects)).toContain('startBatch')
    expect(commitOf(effects)).toBe('hello from batch')
  })

  it('segments arriving during the hold accumulate as live text and ride into the commit', () => {
    const { effects } = run([
      { type: 'HOLD_START' },
      { type: 'STREAM_CONNECTED' },
      { type: 'STREAM_FINAL', text: 'hello' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: OK_STATS },
      { type: 'STREAM_FINAL', text: 'world' }
    ])
    const liveTexts = effects.filter((e) => e.kind === 'setLiveText').map((e) => (e as { text: string }).text)
    expect(liveTexts).toEqual(['', 'hello', 'hello world'])
    expect(commitOf(effects)).toBe('hello world')
  })
})

describe('fallback paths — the stream is never load-bearing', () => {
  const toFinalize: PttEvent[] = [
    { type: 'HOLD_START' },
    { type: 'STREAM_CONNECTED' },
    { type: 'RELEASE' },
    { type: 'DRAINED', stats: OK_STATS }
  ]

  it('finalize deadline expires → batch fallback', () => {
    const { state, effects } = run([...toFinalize, { type: 'FINALIZE_DEADLINE' }])
    expect(state.phase).toBe('batching')
    expect(kinds(effects)).toContain('startBatch')
  })

  it('stream dies during finalize wait → batch fallback instantly', () => {
    const { state, effects } = run([...toFinalize, { type: 'STREAM_DEAD' }])
    expect(state.phase).toBe('batching')
    expect(kinds(effects)).toContain('startBatch')
  })

  it('a late segment after batch fallback is ignored — batch is authoritative (no double commit)', () => {
    const { effects } = run([
      ...toFinalize,
      { type: 'FINALIZE_DEADLINE' },
      { type: 'STREAM_FINAL', text: 'late segment' },
      { type: 'BATCH_OK', transcript: 'batch wins' }
    ])
    expect(effects.filter((e) => e.kind === 'commit')).toHaveLength(1)
    expect(commitOf(effects)).toBe('batch wins')
  })

  it('stream death mid-hold is invisible (no effects) and release batches', () => {
    const midHold = run([{ type: 'HOLD_START' }, { type: 'STREAM_CONNECTED' }, { type: 'STREAM_DEAD' }])
    expect(midHold.state.streamConnected).toBe(false)
    expect(kinds(midHold.effects).filter((k) => k !== 'startCapture' && k !== 'startStream' && k !== 'setLiveText')).toEqual([])
    const done = run([{ type: 'RELEASE' }, { type: 'DRAINED', stats: OK_STATS }], midHold.state)
    expect(done.state.phase).toBe('batching')
  })

  it('batch failure shows the error and returns to idle (no commit)', () => {
    const { state, effects } = run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: OK_STATS },
      { type: 'BATCH_FAIL', message: 'Voice limit reached' }
    ])
    expect(state.phase).toBe('idle')
    expect(commitOf(effects)).toBeNull()
    expect(effects).toContainEqual({ kind: 'showError', message: 'Voice limit reached' })
  })

  it('an empty batch transcript commits "" (caller skips sending)', () => {
    const { effects } = run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: OK_STATS },
      { type: 'BATCH_OK', transcript: '   ' }
    ])
    expect(commitOf(effects)).toBe('')
  })
})

describe('release gates', () => {
  it('too-short → hint + immediate idle (a rapid re-press must not be dropped)', () => {
    const { state, effects } = run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: SHORT_STATS }
    ])
    expect(state.phase).toBe('idle')
    expect(effects).toContainEqual({ kind: 'showHint', hint: 'too-short' })
    expect(commitOf(effects)).toBeNull()
    expect(kinds(effects)).not.toContain('startBatch')
    // Idle means a new HOLD_START works right away.
    expect(reduce(state, { type: 'HOLD_START' }).state.phase).toBe('holding')
  })

  it('silent hold → silent discard: no hint, no network, no commit', () => {
    const { state, effects } = run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: SILENT_STATS }
    ])
    expect(state.phase).toBe('idle')
    expect(kinds(effects)).not.toContain('showHint')
    expect(kinds(effects)).not.toContain('startBatch')
    expect(kinds(effects)).not.toContain('sendFinalize')
    expect(commitOf(effects)).toBeNull()
  })
})

describe('cancel and watchdog — no path can hang or leak', () => {
  const phases: Array<{ name: string; events: PttEvent[] }> = [
    { name: 'holding', events: [{ type: 'HOLD_START' }] },
    { name: 'draining', events: [{ type: 'HOLD_START' }, { type: 'RELEASE' }] },
    {
      name: 'streamFinalize',
      events: [
        { type: 'HOLD_START' },
        { type: 'STREAM_CONNECTED' },
        { type: 'RELEASE' },
        { type: 'DRAINED', stats: OK_STATS }
      ]
    },
    {
      name: 'batching',
      events: [{ type: 'HOLD_START' }, { type: 'RELEASE' }, { type: 'DRAINED', stats: OK_STATS }]
    }
  ]

  for (const { name, events } of phases) {
    it(`CANCEL from ${name} → idle with full teardown and never a commit`, () => {
      const setup = run(events)
      const { state, effects } = run([{ type: 'CANCEL' }], setup.state)
      expect(state.phase).toBe('idle')
      expect(kinds(effects)).toEqual(expect.arrayContaining(['stopCapture', 'stopStream', 'abortBatch']))
      expect(commitOf(effects)).toBeNull()
    })

    it(`WATCHDOG from ${name} → idle with teardown + timeout error`, () => {
      const setup = run(events)
      const { state, effects } = run([{ type: 'WATCHDOG' }], setup.state)
      expect(state.phase).toBe('idle')
      expect(kinds(effects)).toContain('showError')
      expect(commitOf(effects)).toBeNull()
    })
  }

  it('CANCEL and WATCHDOG in idle are no-ops', () => {
    expect(reduce(initialState, { type: 'CANCEL' }).effects).toEqual([])
    expect(reduce(initialState, { type: 'WATCHDOG' }).effects).toEqual([])
  })
})

describe('guards', () => {
  it('HOLD_START is only honored from idle', () => {
    const holding = run([{ type: 'HOLD_START' }])
    const again = reduce(holding.state, { type: 'HOLD_START' })
    expect(again.state.phase).toBe('holding')
    expect(again.effects).toEqual([])
  })

  it('BUFFER_CAPPED warns exactly once and only while holding', () => {
    const holding = run([{ type: 'HOLD_START' }])
    const first = reduce(holding.state, { type: 'BUFFER_CAPPED' })
    expect(first.effects).toContainEqual({ kind: 'showHint', hint: 'too-long' })
    const second = reduce(first.state, { type: 'BUFFER_CAPPED' })
    expect(second.effects).toEqual([])
    expect(reduce(initialState, { type: 'BUFFER_CAPPED' }).effects).toEqual([])
  })

  it('a fresh HOLD_START resets per-capture state (finals, cap warning, connection)', () => {
    const messy = run([
      { type: 'HOLD_START' },
      { type: 'STREAM_CONNECTED' },
      { type: 'STREAM_FINAL', text: 'old' },
      { type: 'BUFFER_CAPPED' },
      { type: 'CANCEL' }
    ])
    const fresh = reduce(messy.state, { type: 'HOLD_START' })
    expect(fresh.state.finals).toEqual([])
    expect(fresh.state.bufferCapped).toBe(false)
    expect(fresh.state.streamConnected).toBe(false)
  })

  it('stale stream events after the capture ended are no-ops', () => {
    const done = run([
      { type: 'HOLD_START' },
      { type: 'RELEASE' },
      { type: 'DRAINED', stats: SILENT_STATS }
    ])
    expect(reduce(done.state, { type: 'STREAM_FINAL', text: 'ghost' }).effects).toEqual([])
    expect(reduce(done.state, { type: 'STREAM_DEAD' }).effects).toEqual([])
    expect(reduce(done.state, { type: 'FINALIZE_DEADLINE' }).effects).toEqual([])
    expect(reduce(done.state, { type: 'BATCH_OK', transcript: 'ghost' }).effects).toEqual([])
  })
})

describe('assembleTranscript', () => {
  it('joins trimmed fragments with single spaces', () => {
    expect(assembleTranscript(['  hello ', 'world  '])).toBe('hello world')
  })
  it('drops whitespace-only fragments', () => {
    expect(assembleTranscript(['hi', '   ', ''])).toBe('hi')
  })
  it('is empty for an empty capture', () => {
    expect(assembleTranscript([])).toBe('')
    expect(assembleTranscript(['  '])).toBe('')
  })
})
