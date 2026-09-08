// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'
import { GoalCelebration, CELEBRATION_TIMINGS } from './GoalCelebration'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const goal = { title: 'Read 24 books', target_value: 24, unit: 'books' }

describe('GoalCelebration', () => {
  it('advances through the phases and fires onDone after the fade + reset', () => {
    const onDone = vi.fn()
    const { container } = render(<GoalCelebration goal={goal} onDone={onDone} />)

    // Phase 1 (dim): scrim only, no text yet.
    expect(container.textContent).not.toContain('Goal Completed!')

    // Phase 3 (text): the celebration text has mounted by textAt.
    act(() => vi.advanceTimersByTime(CELEBRATION_TIMINGS.textAt))
    expect(container.textContent).toContain('Goal Completed!')
    expect(container.textContent).toContain('Read 24 books')
    expect(container.textContent).toContain('24 books reached')

    // onDone must not fire early.
    act(() => vi.advanceTimersByTime(CELEBRATION_TIMINGS.doneAt - CELEBRATION_TIMINGS.textAt - 1))
    expect(onDone).not.toHaveBeenCalled()

    // ...and fires exactly at doneAt.
    act(() => vi.advanceTimersByTime(1))
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('omits the unit from the caption when the goal has none', () => {
    render(<GoalCelebration goal={{ title: 'Ship it', target_value: 1 }} onDone={vi.fn()} />)
    act(() => vi.advanceTimersByTime(CELEBRATION_TIMINGS.textAt))
    expect(document.body.textContent).toContain('1 reached')
    expect(document.body.textContent).not.toContain('undefined')
  })
})
