// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Goals } from './Goals'
import { dashboardIntelligence } from '../lib/intelligence/dashboardStore'
import type { CanonicalGoal } from '../lib/intelligence/wireTypes'

vi.mock('../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: vi.fn(async () => ({ data: [] })), post: vi.fn(), delete: vi.fn() }
}))
vi.mock('../lib/goalsCache', () => ({
  cache: { goals: null, loaded: false },
  hydrateGoalsFromDisk: vi.fn(),
  writeCache: vi.fn()
}))
vi.mock('../lib/agentLLM', () => ({ callAgentLLM: vi.fn(async () => '{"questions": []}') }))
vi.mock('../lib/actionItems', () => ({ fetchAllActionItems: vi.fn(async () => []) }))

const { omiApi } = await import('../lib/apiClient')
const { cache: goalsCache } = await import('../lib/goalsCache')

const legacyGoal = (id: string, title: string): Record<string, unknown> => ({
  id,
  goal_id: id,
  title,
  emoji: '🎯',
  target_value: 10,
  current_value: 2,
  completed: false,
  is_active: true
})

const canonicalGoal = (
  id: string,
  status: CanonicalGoal['status'],
  rank: number | null
): CanonicalGoal => ({
  goalId: id,
  title: `Goal ${id}`,
  desiredOutcome: '',
  whyItMatters: null,
  successCriteria: [],
  status,
  focusRank: rank,
  isActive: true,
  updatedAt: '2026-08-01T00:00:00Z',
  currentValue: null,
  targetValue: null,
  unit: null
})

function stubIntelligence(
  over: Partial<ReturnType<typeof dashboardIntelligence.getState>> = {}
): void {
  vi.spyOn(dashboardIntelligence, 'getState').mockReturnValue({
    accountGeneration: 3,
    recommendations: [],
    goals: [],
    selectedGoalDetail: null,
    goalDetailError: null,
    focusReplacementGoalId: null,
    error: null,
    isLoading: false,
    hasLoadedOnce: true,
    pendingFeedbackCount: 0,
    ...over
  })
  vi.spyOn(dashboardIntelligence, 'subscribe').mockReturnValue(() => {})
  vi.spyOn(dashboardIntelligence, 'load').mockResolvedValue()
}

beforeEach(() => {
  window.localStorage.clear()
  // The page mutates the module cache directly (cache.loaded = true), which
  // would make later mounts skip the fetch; reset it per test.
  ;(goalsCache as { goals: unknown; loaded: boolean }).goals = null
  ;(goalsCache as { goals: unknown; loaded: boolean }).loaded = false
  ;(omiApi.get as ReturnType<typeof vi.fn>).mockImplementation(async (path: string) => {
    if (path === '/v1/goals/all') return { data: [legacyGoal('g-1', 'Ship the launch')] }
    return { data: [] }
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function mount(): void {
  render(
    <MemoryRouter>
      <Goals />
    </MemoryRouter>
  )
}

describe('canonical focus on the Goals page', () => {
  it('legacy accounts see no focus stars', async () => {
    stubIntelligence({ accountGeneration: null })
    mount()
    await waitFor(() => expect(screen.getByText('Ship the launch')).toBeTruthy())
    expect(screen.queryByLabelText('Focus goal')).toBeNull()
    expect(screen.queryByLabelText('Unfocus goal')).toBeNull()
  })

  it('the star focuses an unfocused goal and unfocuses a focused one', async () => {
    stubIntelligence({ goals: [canonicalGoal('g-1', 'background', null)] })
    const focus = vi.spyOn(dashboardIntelligence, 'focus').mockResolvedValue(true)
    mount()
    await waitFor(() => expect(screen.getByText('Ship the launch')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('Focus goal'))
    await waitFor(() => expect(focus).toHaveBeenCalledWith('g-1', null))
  })

  it('a focused goal shows the filled star wired to unfocus', async () => {
    stubIntelligence({ goals: [canonicalGoal('g-1', 'focused', 0)] })
    const unfocus = vi.spyOn(dashboardIntelligence, 'unfocus').mockResolvedValue(true)
    mount()
    await waitFor(() => expect(screen.getByText('Ship the launch')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('Unfocus goal'))
    await waitFor(() => expect(unfocus).toHaveBeenCalledWith('g-1'))
  })

  it('the replacement dialog resends focus with the chosen replacement', async () => {
    stubIntelligence({
      goals: [canonicalGoal('a', 'focused', 0), canonicalGoal('b', 'focused', 1)],
      focusReplacementGoalId: 'g-1'
    })
    const focus = vi.spyOn(dashboardIntelligence, 'focus').mockResolvedValue(true)
    mount()
    await waitFor(() => expect(screen.getByText('Replace a focused goal')).toBeTruthy())
    fireEvent.click(screen.getByLabelText(/Goal a/i, { selector: 'input' }))
    fireEvent.click(screen.getByText('Replace focus'))
    await waitFor(() => expect(focus).toHaveBeenCalledWith('g-1', 'a'))
  })

  it('the subtitle counts focused goals on canonical accounts', async () => {
    stubIntelligence({ goals: [canonicalGoal('g-1', 'focused', 0)] })
    mount()
    await waitFor(() => expect(screen.getByText(/1 focused/)).toBeTruthy())
  })
})
