// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { ModalShell } from './ModalShell'

afterEach(cleanup)

function ThreeButtons(): React.JSX.Element {
  return (
    <ModalShell onClose={vi.fn()}>
      <button>One</button>
      <button>Two</button>
      <button>Three</button>
    </ModalShell>
  )
}

const btn = (name: string): HTMLElement => screen.getByRole('button', { name })

describe('ModalShell focus trap', () => {
  it('focuses the first focusable element on open', () => {
    render(<ThreeButtons />)
    expect(document.activeElement).toBe(btn('One'))
  })

  it('does not steal focus from a child that has autoFocus', () => {
    render(
      <ModalShell onClose={vi.fn()}>
        <button>First</button>
        <input aria-label="named" autoFocus />
      </ModalShell>
    )
    // The autoFocused input keeps focus rather than being overridden by the
    // first-focusable rule.
    expect(document.activeElement).toBe(screen.getByLabelText('named'))
  })

  it('wraps Tab from the last focusable back to the first', () => {
    render(<ThreeButtons />)
    const last = btn('Three')
    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(document.activeElement).toBe(btn('One'))
  })

  it('wraps Shift+Tab from the first focusable back to the last', () => {
    render(<ThreeButtons />)
    const first = btn('One')
    first.focus()
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(btn('Three'))
  })

  it('restores focus to the previously-focused element on unmount', () => {
    const opener = document.createElement('button')
    opener.textContent = 'opener'
    document.body.appendChild(opener)
    opener.focus()
    expect(document.activeElement).toBe(opener)

    const { unmount } = render(<ThreeButtons />)
    // Trap moved focus into the dialog on open...
    expect(document.activeElement).toBe(btn('One'))

    unmount()
    // ...and hands it back to the opener on close.
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
})
