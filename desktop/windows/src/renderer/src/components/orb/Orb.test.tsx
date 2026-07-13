// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'
import { Orb } from './Orb'

// jsdom has no WebGL2 (canvas.getContext('webgl2') → null), so OrbAnimator throws
// on construction — exactly the "WebGL unavailable" path this component must
// survive. The regression: before the fix a failed context left a broken canvas;
// now the canvas stays mounted-but-hidden and the static omi mark shows under it.

afterEach(() => cleanup())

describe('Orb — WebGL-unavailable resilience', () => {
  it('keeps the canvas mounted (for retry) but hidden, and shows the static mark', () => {
    const { container } = render(<Orb size={22} state="idle" />)
    // Canvas is always in the DOM so retries can grab a fresh context…
    const canvas = container.querySelector('canvas')
    expect(canvas).not.toBeNull()
    // …but hidden (opacity 0) until an animator builds — never a visible broken canvas.
    expect(canvas?.style.opacity).toBe('0')
    // …and the static omi mark stands in meanwhile (no broken-image glyph).
    expect(container.querySelector('img')).not.toBeNull()
  })

  it('supersamples the drawing buffer so the shader AA edge stays crisp at bar sizes', () => {
    // The effect sizes canvas.width/height BEFORE building the (here-failing)
    // animator, so the backing store is set even without WebGL. Regression guard
    // for the "misty rim": a buffer sized at only size×dpr made the shader's
    // fixed ~2px AA band a large fraction of a 22–34px orb. It must be
    // supersampled (well above the CSS box) and downscaled by the browser.
    const size = 26
    const { container } = render(<Orb size={size} state="idle" />)
    const canvas = container.querySelector('canvas') as HTMLCanvasElement
    // Backing store is clearly supersampled — well above the CSS box (it would be
    // just `size` at dpr 1 under the old size×dpr sizing, the bug). Bounded on
    // both sides so the guard tracks "supersampled" intent rather than the exact
    // factor, and a runaway backing (a cost blow-up) fails it too.
    expect(canvas.width).toBeGreaterThanOrEqual(size * 2.5)
    expect(canvas.width).toBeLessThanOrEqual(size * 4)
    expect(canvas.height).toBe(canvas.width)
    // CSS box stays the requested size — only the backing store is larger.
    expect(canvas.style.width).toBe(`${size}px`)
  })

  it('retries construction rather than latching immediately', () => {
    vi.useFakeTimers()
    try {
      const { container } = render(<Orb size={26} state="idle" />)
      // Still retrying → static mark still present, canvas still hidden, well
      // before the give-up window (60 × 700ms).
      vi.advanceTimersByTime(5000)
      expect(container.querySelector('img')).not.toBeNull()
      expect(container.querySelector('canvas')?.style.opacity).toBe('0')
    } finally {
      vi.useRealTimers()
    }
  })

  it('remounts a fresh canvas when the context is lost after build (no frozen/broken orb)', () => {
    const { container } = render(<Orb size={26} state="idle" />)
    const first = container.querySelector('canvas') as HTMLCanvasElement
    // A GPU-process reset fires webglcontextlost on the live canvas. Without the
    // recovery handler getContext() keeps returning the dead context → a frozen
    // tiny orb; the fix remounts a brand-new canvas element (keyed on retryNonce).
    act(() => {
      first.dispatchEvent(new Event('webglcontextlost', { cancelable: true }))
    })
    const next = container.querySelector('canvas') as HTMLCanvasElement
    expect(next).not.toBe(first)
  })
})
