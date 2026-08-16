// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { GoalDetailSheet } from './GoalDetailSheet'
import { dashboardIntelligence } from '../../../lib/intelligence/dashboardStore'
import type { GoalDetail } from '../../../lib/intelligence/wireTypes'

vi.mock('../../../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../../../lib/apiClient', () => ({
  omiApi: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
}))

const detail: GoalDetail = {
  goal: {
    goalId: 'g-1',
    title: 'Ship the launch',
    desiredOutcome: 'Launched to everyone',
    whyItMatters: 'The quarter depends on it',
    successCriteria: ['Beta out', 'Zero P0s'],
    status: 'focused',
    focusRank: 0,
    isActive: true,
    updatedAt: '2026-08-01T00:00:00Z',
    currentValue: 2,
    targetValue: 5,
    unit: 'milestones'
  },
  tasks: [{ id: 't1', description: 'Cut the build', completed: false }],
  activeThreads: [{ workstreamId: 'ws1', summary: 'Halfway through packaging' }],
  progressEvents: [{ summary: 'Beta shipped to 50 users' }]
}

function stub(selected: GoalDetail | null, error: string | null = null): void {
  vi.spyOn(dashboardIntelligence, 'getState').mockReturnValue({
    accountGeneration: 3,
    recommendations: [],
    goals: [],
    selectedGoalDetail: selected,
    focusReplacementGoalId: null,
    error,
    isLoading: false,
    pendingFeedbackCount: 0
  })
  vi.spyOn(dashboardIntelligence, 'subscribe').mockReturnValue(() => {})
  vi.spyOn(dashboardIntelligence, 'load').mockResolvedValue()
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('GoalDetailSheet', () => {
  it('renders every populated section from the detail projection', () => {
    stub(detail)
    render(<GoalDetailSheet goalId="g-1" onClose={() => {}} onWorkOnGoal={() => {}} />)
    expect(screen.getByText('Ship the launch')).toBeTruthy()
    expect(screen.getByText('The quarter depends on it')).toBeTruthy()
    expect(screen.getByText('Beta out • Zero P0s')).toBeTruthy()
    expect(screen.getByText('2 / 5 milestones')).toBeTruthy()
    expect(screen.getByText('Halfway through packaging')).toBeTruthy()
    expect(screen.getByText('Beta shipped to 50 users')).toBeTruthy()
  })

  it('the primary work action fires from both the CTA and a thread Continue', () => {
    stub(detail)
    const onWork = vi.fn()
    render(<GoalDetailSheet goalId="g-1" onClose={() => {}} onWorkOnGoal={onWork} />)
    fireEvent.click(screen.getByTestId('goal-work-with-omi-g-1'))
    fireEvent.click(screen.getByText('Continue'))
    expect(onWork).toHaveBeenCalledTimes(2)
  })

  it('shows the loading placeholder while the projection is for another goal', () => {
    stub(null)
    render(<GoalDetailSheet goalId="g-1" onClose={() => {}} onWorkOnGoal={() => {}} />)
    expect(screen.getByText('Loading goal…')).toBeTruthy()
  })

  it('a load failure shows the goal-unavailable error instead of stale content', () => {
    stub(null, 'This goal is no longer available.')
    render(<GoalDetailSheet goalId="g-1" onClose={() => {}} onWorkOnGoal={() => {}} />)
    expect(screen.getByText('This goal is no longer available.')).toBeTruthy()
  })
})
