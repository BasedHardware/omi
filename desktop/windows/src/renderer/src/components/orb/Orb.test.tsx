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
    // Recovery now goes through the shared useWebglRecovery hook (debounced),
    // so the remount lands after its debounce window rather than synchronously.
    vi.useFakeTimers()
    try {
      const { container } = render(<Orb size={26} state="idle" />)
      const first = container.querySelector('canvas') as HTMLCanvasElement
      // A GPU-process reset fires webglcontextlost on the live canvas. Without the
      // recovery handler getContext() keeps returning the dead context → a frozen
      // tiny orb; the fix remounts a brand-new canvas element.
      act(() => {
        first.dispatchEvent(new Event('webglcontextlost', { cancelable: true }))
      })
      // Static mark reappears immediately (ahead of the debounced remount).
      expect(container.querySelector('img')).not.toBeNull()
      act(() => vi.advanceTimersByTime(700))
      const next = container.querySelector('canvas') as HTMLCanvasElement
      expect(next).not.toBe(first)
    } finally {
      vi.useRealTimers()
    }
  })

  it('caps remounts on a context-loss storm so recovery cannot remount unbounded', async () => {
    // Isolate from the construction-retry loop: jsdom always fails REAL WebGL2
    // construction, which on its own remounts a new canvas every ORB_RETRY_MS
    // and would confound a canvas-identity count. Stub OrbAnimator to succeed so
    // the only remounts here come from useWebglRecovery's context-loss recovery
    // (RECOVER_MAX=4 per RECOVER_WINDOW_MS) — the thing under test.
    vi.resetModules()
    /* eslint-disable @typescript-eslint/no-empty-function -- no-op OrbAnimator stub */
    vi.doMock('../../orb/orbAnimator', () => ({
      OrbAnimator: class {
        dispose(): void {}
        setState(): void {}
        setSpeechActive(): void {}
        setVisible(): void {}
        summon(): void {}
        setAmplitude(): void {}
      }
    }))
    /* eslint-enable @typescript-eslint/no-empty-function */
    const { Orb: IsolatedOrb } = await import('./Orb')
    vi.useFakeTimers()
    try {
      const { container } = render(<IsolatedOrb size={26} state="idle" />)
      const canvases = new Set<HTMLCanvasElement>()
      for (let i = 0; i < 8; i++) {
        const current = container.querySelector('canvas') as HTMLCanvasElement
        canvases.add(current)
        // Async + advanceTimersByTimeAsync so the MutationObserver microtask that
        // rebinds useWebglRecovery's listener to the just-remounted canvas gets a
        // chance to run before the next iteration's dispatch (plain
        // advanceTimersByTime never yields to the microtask queue, so the
        // listener would stay stuck on the very first canvas).
        await act(async () => {
          current.dispatchEvent(new Event('webglcontextlost', { cancelable: true }))
          await vi.advanceTimersByTimeAsync(700)
        })
      }
      // Bounded to the cap: the original canvas plus at most 4 recoveries (5
      // total), never one remount per loss (8).
      expect(canvases.size).toBe(5)
    } finally {
      vi.useRealTimers()
      vi.doUnmock('../../orb/orbAnimator')
      vi.resetModules()
    }
  })
})
