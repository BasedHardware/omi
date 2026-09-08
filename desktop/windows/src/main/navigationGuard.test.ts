import { describe, it, expect } from 'vitest'
import { shouldBlockNavigation } from './navigationGuard'

describe('shouldBlockNavigation', () => {
  it('blocks a stray dropped-file navigation (dev http origin)', () => {
    const current = 'http://localhost:5179/'
    expect(shouldBlockNavigation('file:///C:/Users/me/report.pdf', current)).toBe(true)
    expect(shouldBlockNavigation('file:///etc/passwd', current)).toBe(true)
  })

  it('blocks a stray dropped-file navigation (prod loopback http origin)', () => {
    const current = 'http://127.0.0.1:41234/index.html#/home'
    expect(shouldBlockNavigation('file:///C:/Users/me/photo.png', current)).toBe(true)
  })

  it("allows a navigation to the app's own http renderer URL", () => {
    // The app's own origin is never a file: URL in dev/prod, so it is never blocked.
    expect(
      shouldBlockNavigation('http://localhost:5179/index.html', 'http://localhost:5179/')
    ).toBe(false)
    expect(
      shouldBlockNavigation(
        'http://127.0.0.1:41234/index.html#/chat',
        'http://127.0.0.1:41234/index.html'
      )
    ).toBe(false)
  })

  it('does not block external http/https navigations (those route via setWindowOpenHandler)', () => {
    const current = 'http://localhost:5179/'
    expect(shouldBlockNavigation('https://omi.me/pricing', current)).toBe(false)
    expect(shouldBlockNavigation('http://example.com', current)).toBe(false)
    // Stripe checkout completion hop — handled by the checkout window's own will-navigate.
    expect(shouldBlockNavigation('https://checkout.stripe.com/success', current)).toBe(false)
  })

  it('does not block non-web schemes here (mailto/custom — handled by the open handler)', () => {
    const current = 'http://localhost:5179/'
    expect(shouldBlockNavigation('mailto:hi@omi.me', current)).toBe(false)
    expect(shouldBlockNavigation('omi-agent://run', current)).toBe(false)
  })

  it('leaves an unparseable target URL alone', () => {
    const current = 'http://localhost:5179/'
    expect(shouldBlockNavigation('not a url', current)).toBe(false)
    expect(shouldBlockNavigation('', current)).toBe(false)
  })

  describe('file:// loadFile fallback origin', () => {
    const current =
      'file:///C:/Program%20Files/omi/resources/app.asar/out/renderer/index.html#/home'

    it("allows a navigation to the window's own index.html (self, hash stripped)", () => {
      expect(
        shouldBlockNavigation(
          'file:///C:/Program%20Files/omi/resources/app.asar/out/renderer/index.html',
          current
        )
      ).toBe(false)
    })

    it('still blocks a dropped file that is a different local path', () => {
      expect(shouldBlockNavigation('file:///C:/Users/me/report.pdf', current)).toBe(true)
    })
  })
})
