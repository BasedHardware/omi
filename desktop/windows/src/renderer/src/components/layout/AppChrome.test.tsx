// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act, fireEvent, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

// The real Sidebar pulls in Firebase, the R3F orb and window.omi IPC. This suite is
// about WHETHER the rail mounts, not what's in it.
vi.mock('./Sidebar', () => ({ Sidebar: () => <div data-testid="sidebar" /> }))

import { AppChrome } from './AppChrome'
import { setPreferences } from '../../lib/preferences'

// Echoes the current pathname so an Esc-driven navigation is observable.
function Probe(): React.JSX.Element {
  return <div data-testid="path">{useLocation().pathname}</div>
}

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppChrome>
        <Probe />
      </AppChrome>
    </MemoryRouter>
  )
}

const path = (): string | null => screen.getByTestId('path').textContent
const sidebar = (): HTMLElement | null => screen.queryByTestId('sidebar')
const homePill = (): HTMLElement | null => screen.queryByRole('button', { name: 'Home' })

// The Esc handler defers to a macrotask so it can see whether any other listener
// (Rewind's search, a Radix modal) already claimed the key. Tests must flush that.
const pressEscape = (): void => {
  act(() => {
    fireEvent.keyDown(document, { key: 'Escape' })
    vi.advanceTimersByTime(1)
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  localStorage.clear()
  setPreferences({ useLegacyHomeDesign: undefined })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('AppChrome — sidebar retirement', () => {
  it('does NOT render the nav rail by default', () => {
    // The whole point of the change: macOS ships with no sidebar
    // (showsPrimarySidebar = useLegacyHomeDesign && !hideSidebar, default false).
    renderAt('/conversations')
    expect(sidebar()).toBeNull()
  })

  it('renders the nav rail under the legacy flag (kept, not deleted)', () => {
    setPreferences({ useLegacyHomeDesign: true })
    renderAt('/conversations')
    expect(sidebar()).not.toBeNull()
  })

  it('keeps the rail hidden on Settings even in legacy mode (Settings owns its own rail)', () => {
    setPreferences({ useLegacyHomeDesign: true })
    renderAt('/settings')
    expect(sidebar()).toBeNull()
  })
})

describe('AppChrome — PageChromeBar', () => {
  it('shows the Home pill on a non-Home page', () => {
    renderAt('/conversations')
    expect(homePill()).not.toBeNull()
  })

  it('shows the Home pill on Settings (macOS gives Settings the chrome bar too)', () => {
    // Settings ALSO keeps its own rail "Back" control. They are not duplicates:
    // macOS ships both — the pill goes Home, Back goes to the page you came FROM
    // (SettingsSidebar.swift:478-499 + DesktopHomeView.swift:855-862).
    renderAt('/settings')
    expect(homePill()).not.toBeNull()
  })

  it('does NOT show the Home pill on Home', () => {
    renderAt('/home')
    expect(homePill()).toBeNull()
  })

  it('navigates Home when the pill is clicked', () => {
    renderAt('/tasks')
    act(() => {
      fireEvent.click(homePill() as HTMLElement)
    })
    expect(path()).toBe('/home')
  })

  it('is suppressed in legacy mode (the rail is the nav there)', () => {
    setPreferences({ useLegacyHomeDesign: true })
    renderAt('/conversations')
    expect(homePill()).toBeNull()
  })
})

describe('AppChrome — Esc returns Home', () => {
  it.each(['/conversations', '/memories', '/tasks', '/rewind'])('from %s', (p) => {
    renderAt(p)
    pressEscape()
    expect(path()).toBe('/home')
  })

  it('does NOT return Home from Settings', () => {
    // macOS excludes Settings and Apps from onExitCommand (DesktopHomeView.swift:1040).
    renderAt('/settings')
    pressEscape()
    expect(path()).toBe('/settings')
  })

  it('does NOT return Home from Apps', () => {
    renderAt('/apps')
    pressEscape()
    expect(path()).toBe('/apps')
  })

  it('does not steal Esc from a page that already handled it', () => {
    // Rewind's in-page search and Radix modals close on Esc via their own document
    // listeners and call preventDefault. If we navigated Home anyway, closing a
    // modal would also throw the user off the page.
    renderAt('/rewind')
    const claimEsc = (e: KeyboardEvent): void => e.preventDefault()
    document.addEventListener('keydown', claimEsc)
    pressEscape()
    document.removeEventListener('keydown', claimEsc)
    expect(path()).toBe('/rewind')
  })

  it('does not fire while typing in an input', () => {
    renderAt('/tasks')
    const input = document.createElement('input')
    document.body.appendChild(input)
    act(() => {
      fireEvent.keyDown(input, { key: 'Escape' })
      vi.advanceTimersByTime(1)
    })
    expect(path()).toBe('/tasks')
  })
})

describe('AppChrome — Ctrl+N shortcuts', () => {
  it.each([
    ['1', '/home'],
    ['2', '/conversations'],
    ['3', '/memories'],
    ['4', '/tasks'],
    ['5', '/rewind'],
    ['6', '/apps'],
    [',', '/settings']
  ])('Ctrl+%s navigates to %s', (key, expected) => {
    renderAt('/home')
    act(() => {
      fireEvent.keyDown(document, { key, ctrlKey: true })
    })
    expect(path()).toBe(expected)
  })

  it('ignores the shortcut while typing in an input', () => {
    renderAt('/home')
    const input = document.createElement('input')
    document.body.appendChild(input)
    act(() => {
      fireEvent.keyDown(input, { key: '2', ctrlKey: true })
    })
    expect(path()).toBe('/home')
  })
})
