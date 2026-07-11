// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup } from '@testing-library/react'
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
})
