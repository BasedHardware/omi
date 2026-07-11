// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'
import { RevealMarkdown } from './RevealMarkdown'

// Render the (already-tested) markdown as plain text so we can read exactly how
// many characters are on screen at each tick.
vi.mock('../Markdown', () => ({
  Markdown: ({ text }: { text: string }) => <span data-testid="md">{text}</span>
}))

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  cleanup()
})

const FULL = 'A'.repeat(120)

describe('RevealMarkdown', () => {
  it('reveals text progressively rather than jumping to the full string', () => {
    render(<RevealMarkdown text={FULL} startRevealed={false} />)
    const md = (): string => document.querySelector('[data-testid="md"]')!.textContent ?? ''

    // Nothing is shown until the reveal interval starts ticking.
    expect(md().length).toBe(0)

    // One tick reveals a slice — not the whole string.
    act(() => vi.advanceTimersByTime(16))
    const afterOne = md().length
    expect(afterOne).toBeGreaterThan(0)
    expect(afterOne).toBeLessThan(FULL.length)

    // Each subsequent tick grows the visible text monotonically.
    act(() => vi.advanceTimersByTime(16))
    expect(md().length).toBeGreaterThan(afterOne)
    expect(md().length).toBeLessThan(FULL.length)

    // Given enough time it converges on the full string and stops there.
    act(() => vi.advanceTimersByTime(2000))
    expect(md()).toBe(FULL)
  })

  it('renders the full string immediately when startRevealed is true', () => {
    render(<RevealMarkdown text={FULL} startRevealed={true} />)
    const md = document.querySelector('[data-testid="md"]')!.textContent
    // No timers advanced — a non-streaming message must not animate in.
    expect(md).toBe(FULL)
  })
})
