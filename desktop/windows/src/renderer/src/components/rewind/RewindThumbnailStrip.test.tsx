// @vitest-environment jsdom
//
// Idle-burn fix: RewindThumbnailStrip is memoized so a parent (the Rewind page)
// re-rendering for unrelated reasons does not re-render the strip — and its
// per-thumb IntersectionObservers — when none of its own inputs changed. It must
// still re-render when the frame set actually changes (freshness).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createElement } from 'react'
import { render, cleanup } from '@testing-library/react'
import { RewindThumbnailStrip } from './RewindThumbnailStrip'
import type { RewindFrame } from '../../../../shared/types'
// activeStripIndex runs once per render in the strip's body (not memoized inside),
// so its call count is a proxy for "did the strip's render function run".
import { activeStripIndex } from '../../lib/rewindStrip'

vi.mock('../../lib/rewindStrip', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/rewindStrip')>()
  return { ...actual, activeStripIndex: vi.fn(actual.activeStripIndex) }
})

function frame(ts: number, id: number): RewindFrame {
  return {
    id,
    ts,
    app: 'App',
    windowTitle: '',
    processName: '',
    ocrText: '',
    imagePath: `/x-${id}.jpg`,
    width: 0,
    height: 0,
    indexed: 1
  }
}

class NoopObserver {
  observe(): void {
    /* no-op stub */
  }
  unobserve(): void {
    /* no-op stub */
  }
  disconnect(): void {
    /* no-op stub */
  }
}

beforeEach(() => {
  // The strip's thumbs use IntersectionObserver; useElementWidth uses ResizeObserver.
  vi.stubGlobal('IntersectionObserver', NoopObserver)
  vi.stubGlobal('ResizeObserver', NoopObserver)
  ;(window as unknown as { omi: unknown }).omi = {
    rewindFrameImage: vi.fn(async () => null)
  }
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  delete (window as unknown as { omi?: unknown }).omi
})

describe('RewindThumbnailStrip memoization', () => {
  it('does NOT re-render when the parent re-renders with identical props, but DOES when frames change', () => {
    const today = 1_700_000_000_000
    const framesA = [frame(today + 1000, 1), frame(today + 2000, 2)]
    const onSeek = (): void => {} // stable identity across rerenders
    const cursorTs = today + 1000

    const renderCount = (): number =>
      (activeStripIndex as ReturnType<typeof vi.fn>).mock.calls.length
    const wrap = (frames: RewindFrame[]): React.JSX.Element =>
      createElement(RewindThumbnailStrip, { frames, cursorTs, onSeek })

    const { rerender } = render(wrap(framesA))
    const afterMount = renderCount()
    expect(afterMount).toBeGreaterThan(0)

    // Parent re-renders with the SAME props (same frames identity, same cursorTs,
    // same onSeek) — memo must bail out, so the strip's body does not run again.
    rerender(wrap(framesA))
    expect(renderCount()).toBe(afterMount)

    // A genuinely new frame set — the strip must re-render (freshness preserved).
    const framesB = [...framesA, frame(today + 3000, 3)]
    rerender(wrap(framesB))
    expect(renderCount()).toBeGreaterThan(afterMount)
  })
})
