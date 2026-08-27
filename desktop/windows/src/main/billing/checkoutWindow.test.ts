import { describe, expect, it, vi } from 'vitest'

vi.mock('electron', () => ({
  BrowserWindow: {},
  ipcMain: {},
  shell: {}
}))

vi.mock('../contextMenu', () => ({ installContextMenu: vi.fn() }))

import { isAllowedCheckoutStart, outcomeForUrl } from './checkoutWindow'

describe('checkout URL authority', () => {
  it('only starts on Stripe Checkout', () => {
    expect(isAllowedCheckoutStart('https://checkout.stripe.com/c/pay/cs_test')).toBe(true)
    expect(isAllowedCheckoutStart('https://evil.example/pay')).toBe(false)
    expect(isAllowedCheckoutStart('http://checkout.stripe.com/c/pay/cs_test')).toBe(false)
    expect(isAllowedCheckoutStart('https://checkout.stripe.com.evil.example/pay')).toBe(false)
  })

  it('only accepts exact completion paths on the configured API origin', () => {
    const origin = 'https://api.omi.me'
    expect(outcomeForUrl(`${origin}/v1/payments/success`, origin)).toBe('success')
    expect(outcomeForUrl(`${origin}/v1/payments/cancel`, origin)).toBe('cancel')
    expect(outcomeForUrl(`${origin}/v1/payments/success-pretend`, origin)).toBeNull()
    expect(outcomeForUrl('https://evil.example/v1/payments/success', origin)).toBeNull()
  })
})
