import { describe, it, expect } from 'vitest'
import type { AgentPill } from './agentPills'
import {
  pillChipClasses,
  retainTextForPills,
  runDetailFinalText,
  runDetailToProjectionRow,
  synthesizePillTranscript,
  type AgentRunDetail
} from './agentPillTranscript'

function pill(overrides: Partial<AgentPill> = {}): AgentPill {
  return {
    id: 'pill-1',
    runId: 'run_abc',
    sessionId: 'sess-1',
    title: 'Build the thing',
    displayStatus: 'running',
    latestActivity: 'Working…',
    query: 'Build the thing end to end',
    createdAtMs: 1000,
    completedAtMs: null,
    errorMessage: null,
    provider: 'openclaw',
    viewedAtMs: null,
    ...overrides
  }
}

describe('synthesizePillTranscript', () => {
  it('renders query + empty assistant + sending while active (drives the spinner)', () => {
    const { messages, sending } = synthesizePillTranscript(pill(), null)
    expect(messages).toHaveLength(2)
    expect(messages[0]).toMatchObject({ role: 'user', content: 'Build the thing end to end' })
    expect(messages[1]).toMatchObject({ role: 'assistant', content: '' })
    expect(sending).toBe(true)
    // Stable ids so the assistant bubble is not remounted between polls.
    expect(messages[0].id).toBe('pill-1:query')
    expect(messages[1].id).toBe('pill-1:assistant')
  })

  it('shows the evolving assistant text, still sending, before the run finishes', () => {
    const { messages, sending } = synthesizePillTranscript(pill(), 'Partial output so far')
    expect(messages[1]).toMatchObject({ role: 'assistant', content: 'Partial output so far' })
    expect(sending).toBe(true)
  })

  it('settles the final text and stops sending once done', () => {
    const { messages, sending } = synthesizePillTranscript(
      pill({ displayStatus: 'done', completedAtMs: 5000 }),
      'All finished, here is the result.'
    )
    expect(messages[1].content).toBe('All finished, here is the result.')
    expect(sending).toBe(false)
  })

  it('shows a terminal placeholder for a done run with no output (never a blank bubble)', () => {
    const { messages } = synthesizePillTranscript(pill({ displayStatus: 'done' }), '')
    expect(messages[1].content).toBe('Agent finished with no output.')
  })

  it('renders the error bubble for a failed pill (never a silent stall)', () => {
    const { messages, sending } = synthesizePillTranscript(
      pill({ displayStatus: 'failed', errorMessage: 'Adapter crashed' }),
      ''
    )
    expect(messages[1]).toMatchObject({ role: 'assistant', content: 'Adapter crashed' })
    expect(sending).toBe(false)
  })

  it('falls back to a generic failure line when a failed pill has no message', () => {
    const { messages } = synthesizePillTranscript(pill({ displayStatus: 'failed' }), null)
    expect(messages[1].content).toBe('Agent failed')
  })

  it('shows a stopped placeholder when a cancelled run produced no text', () => {
    const { messages } = synthesizePillTranscript(pill({ displayStatus: 'stopped' }), '')
    expect(messages[1].content).toBe('Agent stopped.')
  })

  it('omits the user message when the pill has no query', () => {
    const { messages } = synthesizePillTranscript(pill({ query: '' }), 'hi')
    expect(messages).toHaveLength(1)
    expect(messages[0].role).toBe('assistant')
  })
})

describe('runDetailFinalText', () => {
  it('reads run.finalText', () => {
    expect(runDetailFinalText({ run: { finalText: 'done' } })).toBe('done')
  })
  it('returns empty when absent or non-string', () => {
    expect(runDetailFinalText({ run: {} })).toBe('')
    expect(runDetailFinalText({ run: null })).toBe('')
    expect(runDetailFinalText({ run: { finalText: 42 } })).toBe('')
  })
})

describe('runDetailToProjectionRow', () => {
  it('folds a run detail into a same-pill projection row', () => {
    const detail: AgentRunDetail = {
      run: {
        runId: 'run_abc',
        sessionId: 'sess-1',
        status: 'succeeded',
        finalText: 'Result text',
        completedAtMs: 5000,
        createdAtMs: 1000,
        input: { prompt: 'the original prompt' }
      },
      session: { title: 'Nicer title' }
    }
    const row = runDetailToProjectionRow(pill(), detail)
    expect(row).not.toBeNull()
    expect(row).toMatchObject({
      id: 'pill-1',
      runId: 'run_abc',
      sessionId: 'sess-1',
      title: 'Nicer title',
      status: 'succeeded',
      latestActivity: 'Result text',
      query: 'the original prompt',
      completedAtMs: 5000,
      createdAtMs: 1000
    })
  })

  it('falls back to pill identity/fields when the run omits them', () => {
    const row = runDetailToProjectionRow(pill(), { run: { status: 'running' } })
    expect(row).toMatchObject({
      id: 'pill-1',
      runId: 'run_abc',
      sessionId: 'sess-1',
      title: 'Build the thing',
      status: 'running',
      query: 'Build the thing end to end',
      completedAtMs: null
    })
  })

  it('carries the error message and codes through for a failed run', () => {
    const row = runDetailToProjectionRow(pill(), {
      run: { status: 'failed', errorCode: 'boom', errorMessage: 'it broke' }
    })
    expect(row).toMatchObject({ status: 'failed', errorCode: 'boom', errorMessage: 'it broke' })
  })

  it('returns null when there is no run object', () => {
    expect(runDetailToProjectionRow(pill(), { run: null })).toBeNull()
    expect(runDetailToProjectionRow(pill(), {})).toBeNull()
  })
})

describe('pillChipClasses', () => {
  it('maps each tint token to non-purple Tailwind classes', () => {
    const running = pillChipClasses('running')
    const done = pillChipClasses('done')
    const failed = pillChipClasses('failed')
    const stopped = pillChipClasses('stopped')
    const queued = pillChipClasses('queued')
    expect(running).toContain('amber')
    expect(done).toContain('emerald')
    expect(failed).toContain('red')
    expect(stopped).toContain('neutral')
    expect(queued).toContain('neutral')
    for (const cls of [running, done, failed, stopped, queued]) {
      expect(cls).not.toMatch(/purple|violet|fuchsia|indigo/)
    }
  })
})

describe('retainTextForPills', () => {
  it('drops cached text for pills that no longer exist (eviction/dismiss leak guard)', () => {
    const map = { 'pill-1': 'a', 'pill-2': 'b', 'pill-3': 'c' }
    const kept = retainTextForPills(map, [pill({ id: 'pill-1' }), pill({ id: 'pill-3' })])
    expect(kept).toEqual({ 'pill-1': 'a', 'pill-3': 'c' })
    expect('pill-2' in kept).toBe(false)
  })

  it('returns the SAME reference when every cached id is still live (no churn)', () => {
    const map = { 'pill-1': 'a', 'pill-2': 'b' }
    const same = retainTextForPills(map, [pill({ id: 'pill-1' }), pill({ id: 'pill-2' })])
    expect(same).toBe(map)
  })

  it('prunes everything when no pills remain', () => {
    expect(retainTextForPills({ 'pill-1': 'a' }, [])).toEqual({})
  })
})
