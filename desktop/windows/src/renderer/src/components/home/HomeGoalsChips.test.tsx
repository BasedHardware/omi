// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Hermetic: stub the data layer so the chip row mounts without a live backend or
// Firebase. `currentUser` is set so the auth-gated fetch fires on mount.
const get = vi.fn()
vi.mock('../../lib/apiClient', () => ({ omiApi: { get: (...a: unknown[]) => get(...a) } }))
vi.mock('../../lib/firebase', () => ({
  auth: { currentUser: { uid: 'u1' } },
  onAuthStateChanged: (_a: unknown, cb: (u: { uid: string }) => void) => {
    cb({ uid: 'u1' })
    return () => {}
  }
}))

import { HomeGoalsChips } from './HomeGoalsChips'

function renderChips(props: Parameters<typeof HomeGoalsChips>[0] = {}): void {
  render(
    <MemoryRouter>
      <HomeGoalsChips {...props} />
    </MemoryRouter>
  )
}

beforeEach(() => {
  get.mockReset()
})
afterEach(() => cleanup())

describe('HomeGoalsChips', () => {
  it('renders a chip per active goal with its emoji and a progress bar', async () => {
    get.mockResolvedValue({
      data: [
        { id: 'g1', title: 'Run a marathon', target_value: 26, current_value: 13 },
        { id: 'g2', title: 'Read more books', target_value: 12, current_value: 12 } // done → filtered
      ]
    })
    renderChips()

    // The active goal shows; the completed one is filtered out.
    await screen.findByText('Run a marathon')
    expect(screen.queryByText('Read more books')).toBeNull()

    // Emoji glyph from the shared lookup (run → 🏃) and a color-coded progress fill.
    expect(screen.getByText('🏃')).not.toBeNull()
    const fill = screen.getByTestId('goal-progress-g1') as HTMLElement
    // 13/26 = 50% → yellow band (>=0.4) from the shared progressColor ramp.
    expect(fill.style.width).toBe('50%')
    expect(fill.style.backgroundColor).toBe('rgb(251, 191, 36)')
  })

  it('caps the row at five chips', async () => {
    get.mockResolvedValue({
      data: Array.from({ length: 8 }, (_, i) => ({
        id: `g${i}`,
        title: `Goal ${i}`,
        target_value: 10,
        current_value: 1
      }))
    })
    renderChips()

    await screen.findByText('Goal 0')
    expect(screen.getByText('Goal 4')).not.toBeNull()
    expect(screen.queryByText('Goal 5')).toBeNull()
  })

  it('fires onShowAll when the "All goals" button is clicked', async () => {
    const onShowAll = vi.fn()
    get.mockResolvedValue({ data: [{ id: 'g1', title: 'Ship the app' }] })
    renderChips({ onShowAll })

    fireEvent.click(await screen.findByText('All goals'))
    expect(onShowAll).toHaveBeenCalledTimes(1)
  })

  it('fires onOpenGoal with the goal id when a chip is clicked', async () => {
    const onOpenGoal = vi.fn()
    get.mockResolvedValue({ data: [{ id: 'g1', title: 'Ship the app' }] })
    renderChips({ onOpenGoal })

    fireEvent.click(await screen.findByText('Ship the app'))
    expect(onOpenGoal).toHaveBeenCalledWith('g1')
  })

  it('shows a "Set a goal" chip when there are no active goals, wired to onShowAll', async () => {
    const onShowAll = vi.fn()
    get.mockResolvedValue({ data: [] })
    renderChips({ onShowAll })

    fireEvent.click(await screen.findByText('Set a goal'))
    expect(onShowAll).toHaveBeenCalledTimes(1)
  })

  it('renders the loading skeleton before data resolves', () => {
    get.mockReturnValue(new Promise(() => {})) // never resolves
    renderChips()
    expect(screen.getByTestId('home-goals-chips-loading')).not.toBeNull()
    expect(screen.queryByTestId('home-goals-chips')).toBeNull()
  })

  it('falls back to the empty state (no throw) when the fetch fails', async () => {
    get.mockRejectedValue(new Error('network'))
    renderChips()
    await waitFor(() => expect(screen.getByText('Set a goal')).not.toBeNull())
  })
})
