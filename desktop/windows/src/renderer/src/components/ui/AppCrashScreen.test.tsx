// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, screen, fireEvent } from '@testing-library/react'

// The white-screen net (PR-A / "C1"). Before this, a render-time throw anywhere
// below <App /> unmounted the whole React tree to a blank window for the rest of
// the session — and the renderer process staying alive meant the main-process
// auto-reload never fired. main.tsx now wraps <App /> in this ErrorBoundary with
// <AppCrashScreen /> as its fallback; these assertions are the contract that a
// throwing subtree degrades to the recovery card (heading, body, Reload) instead
// of nothing, and that the boundary is inert when nothing throws.

import { ErrorBoundary } from './ErrorBoundary'
import { AppCrashScreen } from './AppCrashScreen'
import { PanelErrorFallback } from './PanelErrorFallback'

function Thrower(): React.JSX.Element {
  throw new Error('render boom')
}

afterEach(() => {
  cleanup()
})

describe('AppCrashScreen (root error boundary fallback)', () => {
  it('renders the recovery card when the wrapped subtree throws during render', () => {
    // React logs the caught error to console.error — that is the boundary working
    // as designed. Silence the expected noise so the suite output stays clean.
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary label="test" fallback={<AppCrashScreen />}>
        <Thrower />
      </ErrorBoundary>
    )

    expect(screen.getByText('Something went wrong')).toBeTruthy()
    expect(screen.getByText(/unexpected error/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy()

    err.mockRestore()
  })

  it('renders its children untouched when nothing throws (the boundary is inert)', () => {
    render(
      <ErrorBoundary label="test" fallback={<AppCrashScreen />}>
        <div>healthy child</div>
      </ErrorBoundary>
    )

    expect(screen.getByText('healthy child')).toBeTruthy()
    expect(screen.queryByText('Something went wrong')).toBeNull()
  })

  it('Reload reloads the window (the one in-app recovery from a failed boundary)', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    // jsdom's real location.reload() is unimplemented and would throw, so swap in a
    // spy for the duration of the click (restored after).
    const reload = vi.fn()
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, reload }
    })

    try {
      render(
        <ErrorBoundary label="test" fallback={<AppCrashScreen />}>
          <Thrower />
        </ErrorBoundary>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Reload' }))
      expect(reload).toHaveBeenCalledTimes(1)
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation
      })
      err.mockRestore()
    }
  })
})

describe('PanelErrorFallback (per-panel boundary fallback)', () => {
  it('renders its recovery copy and a Reload button', () => {
    render(<PanelErrorFallback />)
    expect(screen.getByText("This page couldn't load")).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy()
  })
})
