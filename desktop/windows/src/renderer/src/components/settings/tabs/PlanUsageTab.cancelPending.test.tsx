// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import { toast } from '../../../lib/toast'

const fetchSubscription = vi.fn()
const startCheckout = vi.fn()

vi.mock('../../../lib/apiClient', () => ({ omiApi: { get: vi.fn(), post: vi.fn() } }))
vi.mock('../../../lib/toast', () => ({ toast: vi.fn() }))
vi.mock('../../../lib/analytics', () => ({
  trackPaywallOpened: vi.fn(),
  trackUpgradeCancelled: vi.fn(),
  trackUpgradePlanSelected: vi.fn(),
  trackUpgradeSucceeded: vi.fn()
}))

vi.mock('../../../lib/billing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/billing')>()
  return {
    ...actual,
    fetchSubscription: (...args: unknown[]) => fetchSubscription(...args),
    fetchChatQuota: vi.fn().mockResolvedValue(null),
    fetchTrial: vi.fn().mockResolvedValue(null),
    fetchOverageInfo: vi.fn().mockResolvedValue(null),
    startCheckout: (...args: unknown[]) => startCheckout(...args),
    openCustomerPortal: vi.fn()
  }
})

const catalog = [
  {
    id: 'operator',
    title: 'Operator',
    prices: [{ id: 'price_op_m', title: 'Monthly', price_string: '$49/mo', interval: 'month' }]
  }
]

function freeSubscription() {
  return {
    subscription: { plan: 'basic', status: 'active', cancel_at_period_end: false },
    available_plans: catalog,
    show_subscription_ui: true
  }
}

beforeEach(() => {
  fetchSubscription.mockReset().mockResolvedValue(freeSubscription())
  startCheckout.mockReset()
  vi.mocked(toast).mockReset()
  ;(window as unknown as { omi: unknown }).omi = { openCheckout: vi.fn() }
})

afterEach(cleanup)

async function openMonthly(): Promise<void> {
  const { PlanUsageTab } = await import('./PlanUsageTab')
  render(
    <SettingsSearchProvider>
      <PlanUsageTab />
    </SettingsSearchProvider>
  )
  await waitFor(() => expect(screen.getByRole('button', { name: 'Select Pro' })).toBeTruthy())
  fireEvent.click(screen.getByRole('button', { name: 'Select Pro' }))
  fireEvent.click(screen.getByRole('button', { name: /Monthly/ }))
}

describe('PlanUsageTab checkout errors', () => {
  it('shows resubscribe-first for an upgrade blocked by a pending cancellation', async () => {
    startCheckout.mockResolvedValue({ kind: 'blocked' })
    await openMonthly()
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith('Resubscribe first to change plans.', { tone: 'error' })
    )
  })

  it('shows the existing-subscription line when checkout reports one', async () => {
    startCheckout.mockResolvedValue({ kind: 'existing_subscription' })
    await openMonthly()
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        'You already have a subscription. Manage your existing subscription instead of starting a new checkout.',
        { tone: 'error' }
      )
    )
    expect(toast).not.toHaveBeenCalledWith('Resubscribe first to change plans.', expect.anything())
  })

  it('shows the error message for any other checkout failure', async () => {
    startCheckout.mockRejectedValue(new Error('stripe down'))
    await openMonthly()
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith('Checkout failed', {
        tone: 'error',
        body: 'stripe down'
      })
    )
  })
})
