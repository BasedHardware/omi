// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, screen, act } from '@testing-library/react'
import { ToastHost } from './ToastHost'
import { toast, dismissToast } from '../../lib/toast'

// The toast() pub/sub shipped with NO host mounted, so every toast() call app-wide
// was a silent no-op (the C/D/E sweep's "no toast" findings). App.tsx now mounts
// this; these assertions are the contract that a dispatched toast actually renders.
// Each test dispatches with duration:0 and dismisses what it adds, leaving the
// module-global queue empty for the next.

afterEach(() => cleanup())

describe('ToastHost', () => {
  it('renders nothing when the queue is empty', () => {
    const { container } = render(<ToastHost />)
    expect(container.firstChild).toBeNull()
  })

  it('renders a dispatched toast title + body', () => {
    render(<ToastHost />)
    let id = 0
    act(() => {
      id = toast('Could not delete task — it has been restored.', {
        tone: 'error',
        duration: 0
      })
    })
    expect(screen.getByText('Could not delete task — it has been restored.')).toBeTruthy()
    act(() => dismissToast(id))
    expect(screen.queryByText('Could not delete task — it has been restored.')).toBeNull()
  })
})
