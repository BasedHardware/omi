// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { RewindTimelineBar } from './RewindTimelineBar'
import type { RewindFrame } from '../../../../shared/types'

// The bar measures its width via ResizeObserver (absent in jsdom); a no-op stub
// leaves it on the built-in fallback width, which is enough to lay out breaks.
/* eslint-disable @typescript-eslint/no-empty-function -- no-op ResizeObserver stub */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

afterEach(cleanup)

const frame = (ts: number): RewindFrame => ({
  ts,
  app: 'App',
  windowTitle: 'w',
  processName: 'p',
  ocrText: '',
  imagePath: '',
  width: 100,
  height: 100,
  indexed: 1
})

const H = 3_600_000

function renderBar(frames: RewindFrame[]): void {
  render(
    <RewindTimelineBar
      frames={frames}
      bounds={null}
      cursorTs={frames.length ? frames[0].ts : 0}
      onSeek={vi.fn()}
    />
  )
}

describe('RewindTimelineBar axis-break gaps', () => {
  it('collapses a large blank stretch into a single vertical break mark', () => {
    // Block A near t=0, block B ~3h later — one gap well over the break threshold.
    renderBar([frame(0), frame(60_000), frame(3 * H), frame(3 * H + 60_000)])
    const breaks = screen.queryAllByTestId('rewind-break')
    expect(breaks).toHaveLength(1)
    // The break carries a vertical zigzag polyline (the cut mark).
    expect(breaks[0].querySelector('polyline')).not.toBeNull()
    // Both activity blocks still render as filled segments beside the break.
    expect(document.querySelectorAll('.bg-white\\/25')).toHaveLength(2)
    // The old horizontal "fill the gap" sawtooth is gone.
    expect(screen.queryAllByTestId('rewind-gap-zigzag')).toHaveLength(0)
  })

  it('emits one break per collapsed gap', () => {
    renderBar([
      frame(0),
      frame(60_000),
      frame(3 * H),
      frame(3 * H + 60_000),
      frame(6 * H),
      frame(6 * H + 60_000)
    ])
    expect(screen.queryAllByTestId('rewind-break')).toHaveLength(2)
  })

  it('draws no break for continuous activity (only sub-threshold gaps)', () => {
    renderBar([frame(0), frame(30_000), frame(60_000)])
    expect(screen.queryAllByTestId('rewind-break')).toHaveLength(0)
  })

  it('keeps the break inert to pointer events so the track stays scrubbable', () => {
    renderBar([frame(0), frame(60_000), frame(3 * H)])
    const brk = screen.getByTestId('rewind-break')
    expect(brk.classList.contains('pointer-events-none')).toBe(true)
  })

  it('renders nothing extra for an empty timeline', () => {
    renderBar([])
    expect(screen.queryAllByTestId('rewind-break')).toHaveLength(0)
  })
})
