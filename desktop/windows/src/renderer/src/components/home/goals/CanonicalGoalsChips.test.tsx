// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CanonicalGoalsChips } from './CanonicalGoalsChips'
import { AllGoalsSheet } from './AllGoalsSheet'
import { GoalCreateSheet } from './GoalCreateSheet'
import { dashboardIntelligence } from '../../../lib/intelligence/dashboardStore'
import type { CanonicalGoal } from '../../../lib/intelligence/wireTypes'

vi.mock('../../../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../../../lib/apiClient', () => ({
  omiApi: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
}))
// The legacy chip row pulls firebase auth at import time; stub it so the
// fallback branch renders without a live auth session.
vi.mock('../HomeGoalsChips', () => ({
  HomeGoalsChips: () => <div data-testid="legacy-goals-chips" />
}))

const goal = (
  id: string,
  status: CanonicalGoal['status'],
  over: Partial<CanonicalGoal> = {}
): CanonicalGoal => ({
  goalId: id,
  title: `Goal ${id}`,
  desiredOutcome: 'Outcome',
  whyItMatters: null,
  successCriteria: [],
  status,
  focusRank: null,
  isActive: true,
  updatedAt: '2026-08-01T00:00:00Z',
  currentValue: null,
  targetValue: null,
  unit: null,
  ...over
})

function stubState(over: Partial<ReturnType<typeof dashboardIntelligence.getState>> = {}): void {
  vi.spyOn(dashboardIntelligence, 'getState').mockReturnValue({
    accountGeneration: 3,
    recommendations: [],
    goals: [],
    selectedGoalDetail: null,
    focusReplacementGoalId: null,
    error: null,
    isLoading: false,
    pendingFeedbackCount: 0,
    ...over
  })
  vi.spyOn(dashboardIntelligence, 'subscribe').mockReturnValue(() => {})
  vi.spyOn(dashboardIntelligence, 'load').mockResolvedValue()
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('CanonicalGoalsChips', () => {
  it('falls back to the legacy chip row outside the intelligence rollout', () => {
    stubState({ accountGeneration: null })
    render(
      <MemoryRouter>
        <CanonicalGoalsChips />
      </MemoryRouter>
    )
    expect(screen.getByTestId('legacy-goals-chips')).toBeTruthy()
    expect(screen.queryByTestId('focused-goals')).toBeNull()
  })

  it('renders the focused subset capped at five with the All goals button', () => {
    stubState({
      goals: [
        goal('a', 'focused', { focusRank: 0 }),
        goal('b', 'focused', { focusRank: 1 }),
        goal('c', 'background'),
        goal('d', 'focused', { focusRank: 2 }),
        goal('e', 'focused', { focusRank: 3 }),
        goal('f', 'focused', { focusRank: 4 }),
        goal('g', 'focused', { focusRank: 5 })
      ]
    })
    render(
      <MemoryRouter>
        <CanonicalGoalsChips />
      </MemoryRouter>
    )
    expect(screen.getByTestId('focused-goals')).toBeTruthy()
    expect(screen.getAllByTestId(/^focused-goal-/)).toHaveLength(5)
    expect(screen.queryByTestId('focused-goal-g')).toBeNull() // sixth focused stays off the row
    expect(screen.queryByText('Goal c')).toBeNull() // background never shows here
    expect(screen.getByText('All goals')).toBeTruthy()
  })

  it('with no focused goals offers Add goal when empty and Choose focus otherwise', () => {
    stubState({ goals: [] })
    const { unmount } = render(
      <MemoryRouter>
        <CanonicalGoalsChips />
      </MemoryRouter>
    )
    expect(screen.getByText('No focused goals')).toBeTruthy()
    expect(screen.getByText('Add goal')).toBeTruthy()
    unmount()

    stubState({ goals: [goal('a', 'background')] })
    render(
      <MemoryRouter>
        <CanonicalGoalsChips />
      </MemoryRouter>
    )
    expect(screen.getByText('Choose focus')).toBeTruthy()
  })
})

describe('AllGoalsSheet', () => {
  it('lists current goals with lifecycle actions and switches to history', () => {
    stubState({ goals: [goal('a', 'focused'), goal('b', 'background'), goal('c', 'achieved')] })
    render(
      <MemoryRouter>
        <AllGoalsSheet onClose={() => {}} onAddGoal={() => {}} onOpenGoal={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('all-goals-row-a')).toBeTruthy()
    expect(screen.getByTestId('all-goals-row-b')).toBeTruthy()
    expect(screen.queryByTestId('all-goals-row-c')).toBeNull()
    expect(screen.getByText('Unfocus')).toBeTruthy() // the focused row's toggle

    fireEvent.click(screen.getByText('History'))
    expect(screen.getByTestId('all-goals-row-c')).toBeTruthy()
    expect(screen.queryByTestId('all-goals-row-a')).toBeNull()
    expect(screen.queryByText('Unfocus')).toBeNull() // history rows carry no mutations
  })

  it('a full focus set opens the replacement sheet and Replace focus resends with the choice', async () => {
    stubState({ goals: [goal('a', 'focused', { focusRank: 0 }), goal('b', 'background')] })
    const focus = vi
      .spyOn(dashboardIntelligence, 'focus')
      .mockImplementationOnce(async () => {
        stubState({
          goals: [goal('a', 'focused', { focusRank: 0 }), goal('b', 'background')],
          focusReplacementGoalId: 'b'
        })
        return false
      })
      .mockResolvedValue(true)
    render(
      <MemoryRouter>
        <AllGoalsSheet onClose={() => {}} onAddGoal={() => {}} onOpenGoal={() => {}} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByText('Focus'))
    await waitFor(() => expect(screen.getByText('Replace a focused goal')).toBeTruthy())
    expect(
      screen.getByText(
        'Your focus set is full. Nothing is archived; the replaced goal moves to All goals.'
      )
    ).toBeTruthy()
    fireEvent.click(screen.getByText('Replace focus'))
    await waitFor(() => expect(focus).toHaveBeenLastCalledWith('b', 'a'))
  })

  it('lifecycle menu drives pause, achieve, and abandon transitions', async () => {
    stubState({ goals: [goal('a', 'background')] })
    const transition = vi.spyOn(dashboardIntelligence, 'transition').mockResolvedValue(true)
    render(
      <MemoryRouter>
        <AllGoalsSheet onClose={() => {}} onAddGoal={() => {}} onOpenGoal={() => {}} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByText('More'))
    fireEvent.click(screen.getByText('Mark achieved'))
    await waitFor(() => expect(transition).toHaveBeenCalledWith('a', 'achieved'))
  })
})

describe('GoalCreateSheet', () => {
  it('requires title and desired outcome, and reuses one occurrence id across retries', async () => {
    stubState()
    const create = vi
      .spyOn(dashboardIntelligence, 'createGoal')
      .mockResolvedValueOnce(false)
      .mockResolvedValue(true)
    const onClose = vi.fn()
    render(<GoalCreateSheet onClose={onClose} />)

    const save = screen.getByTestId('goal-create-save')
    expect((save as HTMLButtonElement).disabled).toBe(true)

    fireEvent.change(screen.getByTestId('goal-create-title'), { target: { value: 'Ship it' } })
    expect((save as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByTestId('goal-create-outcome'), { target: { value: 'Launched' } })
    expect((save as HTMLButtonElement).disabled).toBe(false)

    fireEvent.click(save)
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(onClose).not.toHaveBeenCalled() // failed save keeps the sheet open

    fireEvent.click(save)
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2))
    expect(onClose).toHaveBeenCalled()

    const [, firstOccurrence] = create.mock.calls[0]
    const [, secondOccurrence] = create.mock.calls[1]
    expect(firstOccurrence).toBe(secondOccurrence) // retry reuses the idempotency key
    expect(create.mock.calls[1][0]).toEqual({
      title: 'Ship it',
      desiredOutcome: 'Launched',
      whyItMatters: null,
      successCriteria: []
    })
  })
})
