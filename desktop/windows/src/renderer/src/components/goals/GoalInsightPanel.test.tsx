// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, screen, fireEvent } from '@testing-library/react'
import { GoalInsightPanel } from './GoalInsightPanel'
import type { GoalResponse as Goal } from '../../lib/omiApi.generated'

// The panel drives the shared axios `omiApi` (same as the Goals page), not the
// generated fetch client — stub it so the three states run without a backend.
const omiApiGet = vi.fn()
vi.mock('../../lib/apiClient', () => ({
  omiApi: {
    get: (...args: unknown[]) => omiApiGet(...args),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  },
  desktopApi: { get: vi.fn(), post: vi.fn() }
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const goal = {
  id: 'g1',
  title: 'Read 24 books',
  target_value: 24,
  current_value: 6,
  unit: 'books'
} as Goal

// axios surfaces HTTP errors as `{ response: { status } }`.
const httpError = (status: number): unknown => ({ response: { status } })

describe('GoalInsightPanel', () => {
  it('shows the loading state, then renders the advice', async () => {
    omiApiGet.mockResolvedValue({ data: { advice: 'Read 20 minutes each morning.' } })
    render(<GoalInsightPanel goal={goal} onClose={vi.fn()} />)

    // Loading is shown immediately on mount, before the request resolves.
    expect(screen.getByText(/Getting personalized insight/)).toBeTruthy()

    expect(await screen.findByText('Read 20 minutes each morning.')).toBeTruthy()
    expect(screen.getByText(/This week's action/i)).toBeTruthy()
    expect(omiApiGet).toHaveBeenCalledWith('/v1/goals/g1/advice')
  })

  it('shows an error with Retry, and refetches on Retry', async () => {
    omiApiGet.mockRejectedValueOnce(new Error('network down'))
    omiApiGet.mockResolvedValueOnce({ data: { advice: 'Try again worked.' } })
    render(<GoalInsightPanel goal={goal} onClose={vi.fn()} />)

    expect(await screen.findByText('network down')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('Try again worked.')).toBeTruthy()
    expect(omiApiGet).toHaveBeenCalledTimes(2)
  })

  it('handles a 429 rate limit with a friendly message and disables Refresh', async () => {
    omiApiGet.mockRejectedValue(httpError(429))
    render(<GoalInsightPanel goal={goal} onClose={vi.fn()} />)

    expect(await screen.findByText(/Try again in a moment/i)).toBeTruthy()
    // Cooldown disables both the footer Refresh and the inline Retry so a rapid
    // click can't immediately re-trip the limit.
    expect(screen.getByRole('button', { name: 'Refresh' })).toHaveProperty('disabled', true)
  })

  it('handles a 404 (goal vanished): message, no Refresh, Done still closes', async () => {
    omiApiGet.mockRejectedValue(httpError(404))
    const onClose = vi.fn()
    render(<GoalInsightPanel goal={goal} onClose={onClose} />)

    expect(await screen.findByText(/no longer exists/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Refresh' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
