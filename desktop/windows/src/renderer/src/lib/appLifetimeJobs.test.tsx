// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'

// Regression guard for the Hub port. These four engines used to be kicked off from
// the Home PAGE's mount. Home is now a switch between two designs, so anything that
// changes which component Home renders — or that moves the jobs back into a page —
// would silently stop them in production. This test fails the moment the app shell
// stops starting them.

const maybeBuildLocalGraph = vi.fn()
const maybeStartScreenSynthesis = vi.fn()
const maybeStartInsightEngine = vi.fn()
const maybeStartRetentionSweep = vi.fn()

vi.mock('./kgSynthesis', () => ({ maybeBuildLocalGraph: () => maybeBuildLocalGraph() }))
vi.mock('./screenSynthesis', () => ({
  maybeStartScreenSynthesis: () => maybeStartScreenSynthesis()
}))
vi.mock('./insightEngine', () => ({ maybeStartInsightEngine: () => maybeStartInsightEngine() }))
vi.mock('./retentionSweep', () => ({ maybeStartRetentionSweep: () => maybeStartRetentionSweep() }))

import { useAppLifetimeJobs } from './appLifetimeJobs'

function Shell(): React.JSX.Element {
  useAppLifetimeJobs()
  return <div />
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
})
afterEach(() => {
  vi.useRealTimers()
  cleanup()
})

describe('useAppLifetimeJobs — the shell owns the background engines', () => {
  it('starts screen synthesis, the insight engine, and the retention sweep on mount', () => {
    render(<Shell />)
    expect(maybeStartScreenSynthesis).toHaveBeenCalledTimes(1)
    expect(maybeStartInsightEngine).toHaveBeenCalledTimes(1)
    expect(maybeStartRetentionSweep).toHaveBeenCalledTimes(1)
  })

  it('defers the knowledge-graph build past the entrance animations (1800ms)', () => {
    render(<Shell />)
    // The whole point of the defer: it must NOT run during the entrance.
    expect(maybeBuildLocalGraph).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1800))
    expect(maybeBuildLocalGraph).toHaveBeenCalledTimes(1)
  })

  it('cancels the deferred graph build if the shell unmounts first (sign-out)', () => {
    const { unmount } = render(<Shell />)
    unmount()
    act(() => vi.advanceTimersByTime(5000))
    expect(maybeBuildLocalGraph).not.toHaveBeenCalled()
  })
})
