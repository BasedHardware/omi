import { describe, it, expect } from 'vitest'
import { planFromDecision, type LocalBrainDecision } from './localBrain'

const d = (route: string): LocalBrainDecision => ({ route } as LocalBrainDecision)

describe('localBrain.planFromDecision', () => {
  it('routes sensitive to a confirm', () => {
    expect(planFromDecision(d('confirm_or_refuse'), true)).toEqual({ kind: 'confirm' })
  })

  it('keeps tool intents local when a local LLM is configured', () => {
    for (const r of ['omi_local_memory', 'omi_local_screen_history', 'omi_task_tools']) {
      expect(planFromDecision(d(r), true)).toEqual({ kind: 'local_tools' })
    }
  })

  it('falls back to cloud for tool intents with NO local LLM', () => {
    expect(planFromDecision(d('omi_local_memory'), false)).toEqual({ kind: 'cloud' })
  })

  it('routes easy requests to the local LLM only when one exists', () => {
    expect(planFromDecision(d('small_local_llm'), true)).toEqual({ kind: 'local_llm' })
    expect(planFromDecision(d('small_local_llm'), false)).toEqual({ kind: 'cloud' })
  })

  it('hard requests always go to cloud', () => {
    expect(planFromDecision(d('large_local_llm_or_cloud'), true)).toEqual({ kind: 'cloud' })
  })

  it('is fail-safe: null decision or unknown route -> cloud', () => {
    expect(planFromDecision(null, true)).toEqual({ kind: 'cloud' })
    expect(planFromDecision(d('bogus') as LocalBrainDecision, true)).toEqual({ kind: 'cloud' })
    expect(planFromDecision(d('') as LocalBrainDecision, false)).toEqual({ kind: 'cloud' })
  })
})
