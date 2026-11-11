// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, act, fireEvent, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'

// Settings' rail "Back" control returns to the page you came FROM — macOS semantics
// (SettingsSidebar.swift:478-499, wired to previousIndexBeforeSettings at
// DesktopHomeView.swift:855-862; the dashboard is only its FALLBACK). Windows used to
// hardcode navigate('/home'), i.e. a Home button wearing a Back arrow — that is the
// bug this pins. The separate PageChromeBar "Home" pill is what goes Home.
//
// Only the rail is exercised here; the rest of the Settings page drags in the whole
// settings tab surface (billing, agents, R3F brain map).
vi.mock('../components/settings/SettingsTabPanel', () => ({ SettingsTabPanel: () => null }))
vi.mock('../components/settings/SettingsSearchProvider', () => ({
  SettingsSearchProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>
}))
vi.mock('../components/settings/searchContext', () => ({
  useSettingsSearch: () => ({ query: '', setQuery: () => {} })
}))
vi.mock('../components/settings/tabs', () => ({ SETTINGS_TABS: [] }))
vi.mock('../components/settings/tabs/GeneralTab', () => ({ GeneralTab: () => null }))
vi.mock('../components/settings/tabs/RewindTab', () => ({ RewindTab: () => null }))
vi.mock('../components/settings/tabs/PrivacyTab', () => ({ PrivacyTab: () => null }))
vi.mock('../components/settings/tabs/AccountTab', () => ({ AccountTab: () => null }))
vi.mock('../pages/Memories', () => ({ Memories: () => null }))

import { Settings } from './Settings'

afterEach(cleanup)

function Probe(): React.JSX.Element {
  return <div data-testid="path">{useLocation().pathname}</div>
}

// Enters Settings THROUGH another page, so there is real history to go back to.
function From({ page }: { page: string }): React.JSX.Element {
  const navigate = useNavigate()
  return (
    <>
      <button onClick={() => navigate('/settings')}>open settings</button>
      <div>{page}</div>
    </>
  )
}

function App({ initial }: { initial: string }): React.JSX.Element {
  return (
    <MemoryRouter initialEntries={[initial]}>
      <Probe />
      <Routes>
        <Route path="/tasks" element={<From page="tasks" />} />
        <Route path="/home" element={<From page="home" />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </MemoryRouter>
  )
}

const back = (): HTMLElement => screen.getByRole('button', { name: /back/i })
const path = (): string | null => screen.getByTestId('path').textContent

describe('Settings — rail Back button', () => {
  it('returns to the page you came FROM, not Home', () => {
    render(<App initial="/tasks" />)
    act(() => {
      fireEvent.click(screen.getByText('open settings'))
    })
    expect(path()).toBe('/settings')

    act(() => {
      fireEvent.click(back())
    })
    // The bug: this used to land on /home regardless of where you came from.
    expect(path()).toBe('/tasks')
  })

  it('falls back to Home when Settings is the first entry (opened directly via Ctrl+,)', () => {
    // No history to pop — macOS's dashboard fallback. Without the guard, navigate(-1)
    // would pop out of the app's own history and dead-end.
    render(<App initial="/settings" />)
    act(() => {
      fireEvent.click(back())
    })
    expect(path()).toBe('/home')
  })
})
