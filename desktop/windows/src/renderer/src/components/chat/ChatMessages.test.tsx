// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { ChatMessages } from './ChatMessages'
import type { ChatMsg } from '../../hooks/useChat'

// Render markdown as plain text — we only care about the copy affordance here,
// not how RevealMarkdown paints (that has its own test).
vi.mock('../Markdown', () => ({
  Markdown: ({ text }: { text: string }) => <span data-testid="md">{text}</span>
}))

const writeText = vi.fn().mockResolvedValue(undefined)

beforeEach(() => {
  writeText.mockClear()
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
})
afterEach(() => cleanup())

const assistant = (content: string): ChatMsg => ({ id: 'a1', role: 'assistant', content })
const user = (content: string): ChatMsg => ({ id: 'u1', role: 'user', content })

describe('ChatMessages copy button', () => {
  it('copies the assistant message text and flips to the copied state', async () => {
    render(<ChatMessages messages={[assistant('Hello from omi')]} sending={false} variant="main" />)

    const button = screen.getByRole('button', { name: 'Copy message' })
    fireEvent.click(button)

    expect(writeText).toHaveBeenCalledWith('Hello from omi')
    // The icon swaps to the check-tick, surfaced via the aria-label.
    await screen.findByRole('button', { name: 'Copied' })
  })

  it('offers copy on user messages too (the bar copies both roles)', () => {
    render(
      <ChatMessages messages={[user('what is my day like')]} sending={false} variant="overlay" />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }))
    expect(writeText).toHaveBeenCalledWith('what is my day like')
  })

  it('does not offer copy on the reply that is still streaming in', () => {
    // The last assistant message while `sending` is the in-flight reply — no copy
    // until it settles.
    render(<ChatMessages messages={[assistant('partial repl')]} sending={true} variant="main" />)
    expect(screen.queryByRole('button', { name: 'Copy message' })).toBeNull()
  })

  it('does not offer copy on an empty/whitespace message', () => {
    render(<ChatMessages messages={[assistant('   ')]} sending={false} variant="main" />)
    expect(screen.queryByRole('button', { name: 'Copy message' })).toBeNull()
  })
})
