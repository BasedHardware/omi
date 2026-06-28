import { describe, it, expect } from 'vitest'
import { computeOverlayBounds, OVERLAY_WIDTH, TOP_MARGIN, MAX_HEIGHT_FRACTION } from './bounds'

// A primary display whose work area starts at the origin.
const primary = { x: 0, y: 0, width: 1920, height: 1080 }

describe('computeOverlayBounds', () => {
  it('centers the panel horizontally within the work area', () => {
    const b = computeOverlayBounds(primary, 300)
    expect(b.width).toBe(OVERLAY_WIDTH)
    expect(b.x).toBe(Math.round(primary.x + (primary.width - OVERLAY_WIDTH) / 2))
  })

  it('anchors the top near the top of the work area (fixed margin)', () => {
    const b = computeOverlayBounds(primary, 300)
    expect(b.y).toBe(Math.round(primary.y + TOP_MARGIN))
  })

  it('uses the requested content height when below the clamp', () => {
    const b = computeOverlayBounds(primary, 300)
    expect(b.height).toBe(300)
  })

  it('clamps height to the max fraction of work-area height', () => {
    const tall = 5000
    const b = computeOverlayBounds(primary, tall)
    expect(b.height).toBe(Math.round(primary.height * MAX_HEIGHT_FRACTION))
  })

  it('offsets onto a secondary monitor by its work-area origin', () => {
    const secondary = { x: 1920, y: 0, width: 1280, height: 1024 }
    const b = computeOverlayBounds(secondary, 300)
    expect(b.x).toBe(Math.round(secondary.x + (secondary.width - OVERLAY_WIDTH) / 2))
  })

  it('max-height-clamped panel stays within the work-area bottom edge', () => {
    const shortDisplay = { x: 0, y: 0, width: 1920, height: 500 }
    const b = computeOverlayBounds(shortDisplay, 400)
    expect(b.y + b.height).toBeLessThanOrEqual(shortDisplay.y + shortDisplay.height)
    expect(b.y).toBeGreaterThanOrEqual(shortDisplay.y)
  })

  it('overflow nudge stays structurally satisfied: TOP_MARGIN + maxHeight(0.70) stays on screen', () => {
    // TOP_MARGIN (px) + maxHeight(0.70 * height) <= height for any realistic display,
    // so the panel never runs off the bottom. Locks the invariant so a future constant
    // change re-triggers an on-screen audit.
    const displays = [
      { x: 0, y: 0, width: 1920, height: 1080 },
      { x: 0, y: 0, width: 1280, height: 720 },
      { x: 1920, y: -200, width: 1440, height: 900 }
    ]
    for (const d of displays) {
      const b = computeOverlayBounds(d, Math.round(d.height * MAX_HEIGHT_FRACTION))
      expect(b.y + b.height).toBeLessThanOrEqual(d.y + d.height)
    }
  })
})
