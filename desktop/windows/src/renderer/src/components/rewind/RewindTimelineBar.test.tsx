// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { RewindTimelineBar } from './RewindTimelineBar'
import type { RewindFrame } from '../../../../shared/types'

// The bar measures its width via ResizeObserver (absent in jsdom); a no-op stub
// leaves it on the built-in fallback width, which is enough to lay out the gaps.
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

describe('RewindTimelineBar zigzag gaps', () => {
  it('draws a flatline zigzag through a wide blank stretch between two activity blocks', () => {
    // Block A near t=0, block B ~3h later — one wide gap between them.
    renderBar([frame(0), frame(1000), frame(3 * H), frame(3 * H + 1000)])
    const zigzags = screen.queryAllByTestId('rewind-gap-zigzag')
    // Exactly one gap → exactly one zigzag; both activity blocks stay uncovered.
    expect(zigzags).toHaveLength(1)
    expect(zigzags[0].querySelector('polyline')).not.toBeNull()
    // Two activity blocks render as filled segments beside (not under) the gap.
    expect(document.querySelectorAll('.bg-white\\/25')).toHaveLength(2)
  })

  it('does not draw over continuous activity (no gaps)', () => {
    // All frames within the activity-gap threshold → one segment, no blank.
    renderBar([frame(0), frame(30_000), frame(60_000)])
    expect(screen.queryAllByTestId('rewind-gap-zigzag')).toHaveLength(0)
  })

  it('keeps the zigzag inert to pointer events so the track stays scrubbable', () => {
    renderBar([frame(0), frame(1000), frame(3 * H)])
    const zig = screen.getByTestId('rewind-gap-zigzag')
    expect(zig.classList.contains('pointer-events-none')).toBe(true)
  })

  it('renders nothing extra for an empty timeline', () => {
    renderBar([])
    expect(screen.queryAllByTestId('rewind-gap-zigzag')).toHaveLength(0)
  })
})
