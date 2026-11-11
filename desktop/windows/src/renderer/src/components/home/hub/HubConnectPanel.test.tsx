// @vitest-environment jsdom
import { lazy, type ComponentType } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { HubConnectPanel } from './HubConnectPanel'
import {
  registerHubConnectContent,
  getHubConnectContent,
  preloadHubConnectContent
} from './hubConnectSlot'
import type { HubConnectSlotProps } from './hubConnectSlot'

// The registry is module-global; reset it so tests don't leak into each other.
function resetSlot(): void {
  ;(registerHubConnectContent as unknown as (c: null) => void)(null)
}

afterEach(() => {
  cleanup()
  resetSlot()
})

describe('HubConnectPanel — the Track 3 content slot', () => {
  it('shows the resting "coming soon" state when no content is registered', () => {
    resetSlot()
    render(<HubConnectPanel onDismiss={() => {}} />)
    expect(screen.getByText(/coming soon/i)).not.toBeNull()
  })

  it('renders registered content instead of the resting state, and hands it onDismiss', () => {
    const onDismiss = vi.fn()
    const Tray = ({ onDismiss: close }: HubConnectSlotProps): React.JSX.Element => (
      <button onClick={close}>close tray</button>
    )
    registerHubConnectContent(Tray)

    render(<HubConnectPanel onDismiss={onDismiss} />)

    // The resting copy is gone; the tray is mounted.
    expect(screen.queryByText(/coming soon/i)).toBeNull()
    // And the panel wired the Hub's dismiss straight through to the tray.
    fireEvent.click(screen.getByText('close tray'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('registration is readable back through the getter (the seam Track 3 uses)', () => {
    resetSlot()
    expect(getHubConnectContent()).toBeNull()
    const Tray = (): React.JSX.Element => <div />
    registerHubConnectContent(Tray)
    expect(getHubConnectContent()).toBe(Tray)
  })

  // Regression: the reported bug was the empty "coming soon" copy flashing while the
  // lazy connections chunk was still importing on first open — a LOADING state must
  // never render the EMPTY state's copy.
  it('shows a loading state (not the "coming soon" copy) while the lazy tray chunk imports', () => {
    // A tray registered as React.lazy whose import never resolves within the test —
    // exactly the first-open path where the chunk is still importing and Suspense shows
    // its fallback. That fallback must be the loading indicator, not the empty copy.
    const LazyTray = lazy(
      () => new Promise<{ default: ComponentType<HubConnectSlotProps> }>(() => {})
    )
    registerHubConnectContent(LazyTray)

    render(<HubConnectPanel onDismiss={() => {}} />)

    expect(screen.queryByText(/coming soon/i)).toBeNull()
    expect(screen.getByTestId('hub-connect-loading')).not.toBeNull()
  })
})

describe('hubConnectSlot — chunk preload (cache-first first open)', () => {
  // The connections tray is a static curated list (no per-uid data to snapshot), so its
  // "render instantly" cache is the lazy chunk itself: warming it before first open is
  // what removes the loading gap. These lock the seam HomeHub uses to warm it.
  it('preloadHubConnectContent warms the registered tray through its preloader', () => {
    const Tray = (): React.JSX.Element => <div />
    const preload = vi.fn()
    registerHubConnectContent(Tray, preload)

    preloadHubConnectContent()

    expect(preload).toHaveBeenCalledTimes(1)
  })

  it('preloadHubConnectContent is a no-op when nothing (or no preloader) is registered', () => {
    resetSlot()
    expect(() => preloadHubConnectContent()).not.toThrow()

    // A tray registered without a preloader must also not throw when warmed.
    registerHubConnectContent((): React.JSX.Element => <div />)
    expect(() => preloadHubConnectContent()).not.toThrow()
  })
})
