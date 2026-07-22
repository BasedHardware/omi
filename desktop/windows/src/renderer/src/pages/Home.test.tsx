// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act, screen } from '@testing-library/react'

// Home is a switch between the Hub (default) and the original design, driven by the
// `useLegacyHomeDesign` preference. Both directions are asserted, and so is the live
// swap — flipping the toggle in Settings must not need a restart.

vi.mock('./LegacyHome', () => ({ LegacyHome: () => <div data-testid="legacy" /> }))
vi.mock('../components/home/hub/HomeHub', () => ({ HomeHub: () => <div data-testid="hub" /> }))

import { Home } from './Home'
import { setPreferences } from '../lib/preferences'

beforeEach(() => {
  localStorage.clear()
  setPreferences({ useLegacyHomeDesign: undefined })
})
afterEach(cleanup)

describe('Home — legacy-design switch', () => {
  it('renders the Hub by default (no preference set)', () => {
    render(<Home />)
    expect(screen.queryByTestId('hub')).not.toBeNull()
    expect(screen.queryByTestId('legacy')).toBeNull()
  })

  it('renders the original Home when the preference is on', () => {
    setPreferences({ useLegacyHomeDesign: true })
    render(<Home />)
    expect(screen.queryByTestId('legacy')).not.toBeNull()
    expect(screen.queryByTestId('hub')).toBeNull()
  })

  it('swaps live in BOTH directions when the preference changes (no restart)', () => {
    render(<Home />)
    expect(screen.queryByTestId('hub')).not.toBeNull()

    act(() => setPreferences({ useLegacyHomeDesign: true }))
    expect(screen.queryByTestId('legacy')).not.toBeNull()
    expect(screen.queryByTestId('hub')).toBeNull()

    act(() => setPreferences({ useLegacyHomeDesign: false }))
    expect(screen.queryByTestId('hub')).not.toBeNull()
    expect(screen.queryByTestId('legacy')).toBeNull()
  })
})
