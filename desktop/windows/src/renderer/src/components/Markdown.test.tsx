// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, screen, fireEvent, waitFor } from '@testing-library/react'
import { Markdown } from './Markdown'

// jsdom ships no clipboard; define a mock writeText so the code-block copy button
// has something to call.
const writeText = vi.fn(() => Promise.resolve())

beforeEach(() => {
  writeText.mockClear()
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true
  })
})
afterEach(() => cleanup())

const CODE = 'const x = 1\nconsole.log(x)'

describe('Markdown — fenced code block copy button', () => {
  it('copies the raw fenced code text and flips the icon to a check', async () => {
    render(<Markdown text={'```\n' + CODE + '\n```'} />)

    const btn = screen.getByRole('button', { name: 'Copy code' })
    fireEvent.click(btn)

    // The button copies the exact code text (no fence markers, no trailing newline).
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(CODE))
    // Feedback: the affordance switches to the "Copied" (check) state.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Copied' })).not.toBeNull())
    expect(screen.queryByRole('button', { name: 'Copy code' })).toBeNull()
  })

  it('adds no copy button to inline code', () => {
    render(<Markdown text={'here is `inline` code'} />)
    expect(screen.queryByRole('button', { name: 'Copy code' })).toBeNull()
  })

  it('renders one copy button per fenced block', () => {
    render(<Markdown text={'```\na\n```\n\ntext\n\n```\nb\n```'} />)
    expect(screen.getAllByRole('button', { name: 'Copy code' })).toHaveLength(2)
  })
})
