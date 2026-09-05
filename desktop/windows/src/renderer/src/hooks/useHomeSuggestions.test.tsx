// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen, waitFor } from '@testing-library/react'
import { useHomeSuggestions } from './useHomeSuggestions'
import {
  __resetSuggestionsGenerationForTest,
  LEAD_SUGGESTION
} from '../lib/intelligence/homeSuggestions'

vi.mock('../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: vi.fn(async () => ({ data: [] })), post: vi.fn(), delete: vi.fn() }
}))
vi.mock('../lib/agentLLM', () => ({ callAgentLLM: vi.fn(async () => '{"questions": []}') }))
vi.mock('../lib/actionItems', () => ({ fetchAllActionItems: vi.fn(async () => []) }))

function Probe(): React.JSX.Element {
  const suggestions = useHomeSuggestions()
  return (
    <ol>
      {suggestions.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ol>
  )
}

beforeEach(() => {
  window.localStorage.clear()
  __resetSuggestionsGenerationForTest()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('useHomeSuggestions', () => {
  it('always composes the lead chip plus two questions, from fallbacks when nothing is cached', async () => {
    render(<Probe />)
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(3))
    const texts = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(texts[0]).toBe(LEAD_SUGGESTION)
    expect(texts[1]).toBe('What did I spend my time on this week?')
  })

  it('publishes a cached personalized set immediately, before any refresh lands', async () => {
    window.localStorage.setItem(
      'homePersonalizedSuggestions.v1.uid-1',
      JSON.stringify({ questions: ['Ask Sam about the launch?'], dayStamp: '2000-01-01' })
    )
    render(<Probe />)
    // The stale-day cache still publishes first render; the refresh then runs.
    expect(screen.getAllByRole('listitem')[1].textContent).toBe('Ask Sam about the launch?')
  })
})
