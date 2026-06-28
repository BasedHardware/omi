import { describe, it, expect } from 'vitest'
import { isPaymentSensitive } from './paymentGuard'
import type { AutomationPlan } from './types'

function plan(p: Partial<AutomationPlan>): AutomationPlan {
  return { summary: '', targetWindow: '', steps: [], ...p } as AutomationPlan
}

describe('payment guard', () => {
  it('flags checkout / payment summaries', () => {
    expect(isPaymentSensitive(plan({ summary: 'Complete the checkout' }))).toBe(true)
    expect(isPaymentSensitive(plan({ summary: 'Place the order and pay' }))).toBe(true)
    expect(isPaymentSensitive(plan({ targetWindow: 'PayPal - Checkout' }))).toBe(true)
  })

  it('flags card details typed into a field', () => {
    expect(
      isPaymentSensitive(plan({ steps: [{ type: 'set_value', elementRef: 'a:Card number', value: '4111' }] as any }))
    ).toBe(true)
  })

  it('flags a "Buy now" / "Confirm and pay" click context', () => {
    expect(isPaymentSensitive(plan({ summary: 'Click Buy now' }))).toBe(true)
    expect(isPaymentSensitive(plan({ steps: [{ type: 'click', elementRef: 'a:Confirm and pay' }] as any }))).toBe(true)
  })

  it('does NOT flag ordinary actions', () => {
    expect(isPaymentSensitive(plan({ summary: 'Reply to the email', steps: [{ type: 'set_value', elementRef: 'a:Body', value: 'Hi there' }] as any }))).toBe(false)
    expect(isPaymentSensitive(plan({ summary: 'Open the settings page' }))).toBe(false)
  })
})
