// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { HubConnectPanel } from './HubConnectPanel'
import { registerHubConnectContent, getHubConnectContent } from './hubConnectSlot'
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
})
