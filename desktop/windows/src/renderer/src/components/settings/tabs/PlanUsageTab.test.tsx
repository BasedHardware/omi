// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

// PR-D: a 200 response that lacks `.subscription` (or a null body) used to render
// literally nothing (`return <></>`), leaving a blank panel. It must instead show
// a friendly "couldn't load" state with a retry — same shape as the outright-error
// state. We mock only the four network fetchers; the pure billing helpers are not
// exercised on this branch (subscription is absent, so `orderedCatalog` /
// `isTrialActive` are never called), so leaving them off the mock is safe.

const fetchSubscription = vi.fn()
const fetchChatQuota = vi.fn()
const fetchTrial = vi.fn()
const fetchOverageInfo = vi.fn()

vi.mock('../../../lib/billing', () => ({
  fetchSubscription: (...a: unknown[]) => fetchSubscription(...a),
  fetchChatQuota: (...a: unknown[]) => fetchChatQuota(...a),
  fetchTrial: (...a: unknown[]) => fetchTrial(...a),
  fetchOverageInfo: (...a: unknown[]) => fetchOverageInfo(...a)
}))
vi.mock('../../../lib/toast', () => ({ toast: vi.fn() }))

beforeEach(() => {
  // A 200 with no `.subscription` field — the unexpected shape that produced a
  // blank panel before this fix.
  fetchSubscription.mockReset().mockResolvedValue({})
  fetchChatQuota.mockReset().mockResolvedValue(null)
  fetchTrial.mockReset().mockResolvedValue(null)
  fetchOverageInfo.mockReset().mockResolvedValue(null)
  ;(window as unknown as { omi: unknown }).omi = {}
})

afterEach(cleanup)

async function renderTab(): Promise<void> {
  const { PlanUsageTab } = await import('./PlanUsageTab')
  render(
    <SettingsSearchProvider>
      <PlanUsageTab />
    </SettingsSearchProvider>
  )
}

describe('PlanUsageTab — unexpected shape (PR-D)', () => {
  it('shows friendly copy + a retry instead of a blank panel when `.subscription` is missing', async () => {
    await renderTab()

    await waitFor(() =>
      expect(screen.queryByText('Couldn’t load your plan details.')).not.toBeNull()
    )
    expect(screen.getByRole('button', { name: /Try again/i })).not.toBeNull()
  })

  it('Try again re-fetches the subscription', async () => {
    await renderTab()

    await waitFor(() => expect(fetchSubscription).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }))
    await waitFor(() => expect(fetchSubscription).toHaveBeenCalledTimes(2))
  })
})
