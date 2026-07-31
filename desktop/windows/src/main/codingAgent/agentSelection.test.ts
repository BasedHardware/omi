import { describe, expect, it } from 'vitest'
import { rankAgentsForTask, scoreAgentForTask } from './agentSelection'
import type { CodingAgentAdapterId } from './interface'

const ALL: CodingAgentAdapterId[] = ['acp', 'openclaw', 'hermes', 'codex']

describe('scoreAgentForTask', () => {
  it('is neutral (ties) for a prompt with no tool/duration signal', () => {
    const scores = ALL.map((id) => scoreAgentForTask(id, 'hey there'))
    expect(new Set(scores).size).toBe(1)
  })

  it('penalizes OpenClaw for tool-heavy prompts (it cannot use Omi tools)', () => {
    const toolPrompt = 'fix the failing test in my repo and run the build'
    expect(scoreAgentForTask('openclaw', toolPrompt)).toBeLessThan(
      scoreAgentForTask('acp', toolPrompt)
    )
    expect(scoreAgentForTask('openclaw', toolPrompt)).toBeLessThan(0)
  })

  it('rewards native-resume agents for long-running/continuation prompts', () => {
    const longPrompt = 'keep working on this over the next hour, resume where you left off'
    expect(scoreAgentForTask('acp', longPrompt)).toBeGreaterThan(
      scoreAgentForTask('hermes', longPrompt)
    )
  })
})

describe('rankAgentsForTask', () => {
  it('preserves input order when nothing distinguishes the agents', () => {
    expect(rankAgentsForTask(['openclaw', 'acp', 'codex'], '')).toEqual([
      'openclaw',
      'acp',
      'codex'
    ])
  })

  it('moves OpenClaw behind tool-capable agents for a tool-heavy task', () => {
    const ranked = rankAgentsForTask(['openclaw', 'acp', 'hermes'], 'run the tests and fix bugs')
    expect(ranked.indexOf('openclaw')).toBeGreaterThan(ranked.indexOf('acp'))
    expect(ranked.indexOf('openclaw')).toBeGreaterThan(ranked.indexOf('hermes'))
  })

  it('never reorders a single-candidate list', () => {
    expect(rankAgentsForTask(['codex'], 'run the tests and fix bugs')).toEqual(['codex'])
  })
})
