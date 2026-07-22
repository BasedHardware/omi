// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { GoalResponse as Goal } from '../lib/omiApi.generated'

// PR-D: a data page must distinguish a FAILED fetch from a genuinely EMPTY
// result. When `/v1/goals/all` fails, the page must show friendly copy AND must
// NOT show the "No goals yet" empty state (which falsely implies the account has
// no goals). When the fetch succeeds with zero goals, the empty state DOES show.

const getMock = vi.fn()
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: (...args: unknown[]) => getMock(...args) }
}))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

const goal = (over: Partial<Goal>): Goal =>
  ({
    id: 'g1',
    title: 'Read more',
    target_value: 10,
    current_value: 0,
    unit: 'books',
    is_active: true,
    ...over
  }) as Goal

beforeEach(() => {
  getMock.mockReset()
  localStorage.clear()
  // onGoalsChanged is optional-chained in the page; provide a no-op subscription
  // so the effect's cleanup is a real function.
  ;(window as unknown as { omi: unknown }).omi = {
    onGoalsChanged: vi.fn(() => () => {})
  }
})

afterEach(() => {
  cleanup()
  vi.resetModules()
})

async function renderGoals(): Promise<void> {
  const { Goals } = await import('./Goals')
  render(
    <MemoryRouter>
      <Goals />
    </MemoryRouter>
  )
}

describe('Goals — error vs empty', () => {
  it('a failed fetch shows friendly copy and NOT the "No goals yet" empty state', async () => {
    getMock.mockRejectedValue(new Error('Request failed with status code 500'))
    await renderGoals()

    await waitFor(() => expect(screen.queryByText('Couldn’t load your goals.')).not.toBeNull())
    // The misleading empty state must be suppressed while there is an error.
    expect(screen.queryByText('No goals yet')).toBeNull()
  })

  it('a genuinely empty (successful) fetch shows the "No goals yet" empty state', async () => {
    getMock.mockResolvedValue({ data: [] })
    await renderGoals()

    await waitFor(() => expect(screen.queryByText('No goals yet')).not.toBeNull())
    expect(screen.queryByText('Couldn’t load your goals.')).toBeNull()
  })

  it('Try again re-fetches; a recovered fetch clears the error and renders goals', async () => {
    getMock
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue({ data: [goal({ id: 'g1', title: 'Read more' })] })
    await renderGoals()

    await waitFor(() => expect(screen.queryByText('Couldn’t load your goals.')).not.toBeNull())
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }))

    await waitFor(() => expect(screen.queryByText('Read more')).not.toBeNull())
    expect(screen.queryByText('Couldn’t load your goals.')).toBeNull()
  })

  it('a failed revalidation over cached goals stays silent (cache-first, no alarm)', async () => {
    // A prior session persisted goals; on cold start they hydrate immediately.
    localStorage.setItem('omi.lastSignedInUid', 'u1')
    localStorage.setItem(
      'omi.cache.goals.u1',
      JSON.stringify([goal({ id: 'cached', title: 'Cached goal' })])
    )
    // The revalidating fetch fails (offline restart).
    getMock.mockRejectedValue(new Error('offline'))
    await renderGoals()

    // The cached goal is on screen...
    await waitFor(() => expect(screen.queryByText('Cached goal')).not.toBeNull())
    // ...and the failed revalidation does NOT show the alarming banner or empty state.
    expect(screen.queryByText('Couldn’t load your goals.')).toBeNull()
    expect(screen.queryByText('No goals yet')).toBeNull()
  })

  it('does not persist goals cross-account when the account switches mid-fetch', async () => {
    localStorage.setItem('omi.lastSignedInUid', 'userA')
    // The fetch resolves AFTER a switch to userB (teardown already ran, uid flipped).
    getMock.mockImplementation(async () => {
      localStorage.setItem('omi.lastSignedInUid', 'userB')
      return { data: [goal({ id: 'a-goal', title: 'A goal' })] }
    })
    await renderGoals()
    await waitFor(() => expect(getMock).toHaveBeenCalled())

    // A's goals must NOT be written under B's uid (nor re-created under A's).
    expect(localStorage.getItem('omi.cache.goals.userB')).toBeNull()
    expect(localStorage.getItem('omi.cache.goals.userA')).toBeNull()
  })
})
