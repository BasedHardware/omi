// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { RewindPlayer } from './RewindPlayer'

// RewindPlayer measures its container via ResizeObserver (absent in jsdom); a
// no-op stub keeps the mount from throwing.
/* eslint-disable @typescript-eslint/no-empty-function -- no-op ResizeObserver stub */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

afterEach(cleanup)

describe('RewindPlayer — loading gate', () => {
  it('does not flash the misleading "No frames yet" state while still loading', () => {
    render(<RewindPlayer frames={[]} cursorTs={0} loading />)
    // The frames may already exist — while loading we show a neutral placeholder,
    // NOT "enable Rewind capture in Settings".
    expect(screen.queryByText(/No frames yet/)).toBeNull()
    expect(screen.queryByText('Loading…')).not.toBeNull()
  })

  it('shows the "No frames yet" empty state once loading is done with no frames', () => {
    render(<RewindPlayer frames={[]} cursorTs={0} loading={false} />)
    expect(screen.queryByText(/No frames yet/)).not.toBeNull()
  })
})
