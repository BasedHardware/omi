import { beforeEach, expect, it, vi, type MockInstance } from 'vitest'
vi.mock('./firebase', () => ({ auth: { currentUser: null } }))
import { openSubscriptionCheckout, trackUpgradePlanSelected, trackPurchaseEvent } from './analytics'
import {
  PurchaseObservation,
  purchasePayload,
  purchaseContract
} from './purchaseContract.generated'
let fetchMock: MockInstance<typeof fetch>
const names = () =>
  fetchMock.mock.calls.map((call) => JSON.parse(String((call[1] as RequestInit).body)).event)
beforeEach(() => {
  vi.restoreAllMocks()
  fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response())
})
it('tap, actual open callback, success navigation are three different boundaries', async () => {
  trackUpgradePlanSelected('unlimited_v2', 'Monthly', 'windows_settings_view')
  let opened!: () => void
  let finish!: (result: 'success') => void
  const flow = openSubscriptionCheckout(
    (_url, onOpened) => {
      opened = onOpened!
      return new Promise((resolve) => {
        finish = resolve
      })
    },
    'https://checkout.stripe.test/private',
    'unlimited_v2',
    'Monthly',
    'windows_settings_view'
  )
  expect(names()).toContain('Subscription Upgrade Tapped')
  expect(names()).not.toContain('Subscription Checkout Opened')
  opened()
  opened()
  expect(names().filter((e) => e === 'Subscription Checkout Opened')).toHaveLength(1)
  expect(names()).not.toContain('Subscription Checkout Completed')
  finish('success')
  await flow
  expect(names().filter((e) => e === 'Subscription Checkout Completed')).toHaveLength(1)
  expect(JSON.stringify(fetchMock.mock.calls.map((c) => c[1]))).not.toContain('private')
})
it.each(['cancel', 'closed', 'error'] as const)('never completes %s', async (outcome) => {
  const open = vi.fn(async (_url: string, onOpened?: () => void) => {
    onOpened?.()
    if (outcome === 'error') throw new Error('private')
    return outcome
  })
  await openSubscriptionCheckout(
    open,
    'https://checkout.stripe.test/private',
    'plus',
    'month',
    'windows_settings_view'
  ).catch(() => {})
  expect(names()).not.toContain('Subscription Checkout Completed')
})
it('views and authoritative reach/block deduplicate separately and rearm on recovery', () => {
  const observer = new PurchaseObservation(trackPurchaseEvent)
  const view = {
    source: 'windows_settings_view',
    surface: 'settings_plans',
    current_plan: 'basic',
    catalog_tier: 'not_applicable'
  }
  observer.view(view)
  observer.view(view)
  const limit = { allowance_kind: 'chat', surface: 'chat', reason: 'chat_quota_exhausted' }
  observer.allowance(true, limit)
  observer.allowance(true, limit)
  expect(names()).not.toContain('Subscription Allowance Block Shown')
  observer.allowance(true, limit, true)
  observer.allowance(true, limit, true)
  observer.allowance(false, limit)
  observer.allowance(true, limit)
  expect(names().filter((e) => e === 'Subscription Paywall Viewed')).toHaveLength(1)
  expect(names().filter((e) => e === 'Subscription Allowance Reached')).toHaveLength(2)
  expect(names().filter((e) => e === 'Subscription Allowance Block Shown')).toHaveLength(1)
})
it('all generated events strip unknown keys and free values at runtime', () => {
  for (const id of Object.keys(purchaseContract) as (keyof typeof purchaseContract)[]) {
    const result = purchasePayload(id, {
      source: 'private',
      plan: 'private',
      url: 'private',
      uid: 'private',
      error: 'private'
    })
    expect(JSON.stringify(result)).not.toContain('private')
    for (const [key, value] of Object.entries(result.properties)) {
      expect((purchaseContract[id].properties as Record<string, readonly string[]>)[key]).toContain(
        value
      )
    }
  }
})

it('server quota observation ignores optimistic local exhaustion', async () => {
  const { createChatQuotaGate } = await import('./chatQuotaGate')
  const gate = createChatQuotaGate(vi.fn())
  const snapshot = { allowed: true, plan: 'basic', unit: 'questions', used: 0, limit: 1 } as any
  gate.applyQuota(snapshot)
  gate.recordQuery()
  expect(gate.isLimitReached()).toBe(true)
  expect(names()).not.toContain('Subscription Allowance Reached')
  gate.applyQuota({ ...snapshot, allowed: false })
  gate.applyQuota({ ...snapshot, allowed: false })
  expect(names().filter((e) => e === 'Subscription Allowance Reached')).toHaveLength(1)
  gate.applyQuota(snapshot)
  gate.applyQuota({ ...snapshot, allowed: false })
  expect(names().filter((e) => e === 'Subscription Allowance Reached')).toHaveLength(2)
  expect(names()).not.toContain('Subscription Allowance Block Shown')
})
