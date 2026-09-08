// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// useMemories, the Calendar status probe, and useGoogleConnection all fetch on
// mount; keep them offline. One mock for every GET: callers read .memories or
// .connected — both fall out to empty/false, which every tile/row renders fine.
const { omiGet } = vi.hoisted(() => ({ omiGet: vi.fn() }))
vi.mock('../../../../lib/apiClient', () => ({
  omiApi: { get: omiGet, post: vi.fn(), delete: vi.fn() },
  desktopApi: { post: vi.fn() }
}))
// The X tile/row mints a session from Firebase; keep it signed-out (null) here so
// the X status/run probes never fire.
vi.mock('../../../../lib/firebase', () => ({ auth: { currentUser: null } }))

import { ConnectionsPanel } from './ConnectionsPanel'
import { getHubConnectContent } from '../hubConnectSlot'

let openExternalUrl: ReturnType<typeof vi.fn>

beforeEach(() => {
  omiGet.mockResolvedValue({ data: { memories: [], connected: false } })
  openExternalUrl = vi.fn()
  ;(window as unknown as { omi: Record<string, unknown> }).omi = {
    openExternalUrl,
    readStickyNotes: vi.fn(),
    googleStatus: vi.fn().mockResolvedValue({ connected: false }),
    xStatus: vi
      .fn()
      .mockResolvedValue({ connected: false, postCount: 0, memoryCount: 0, syncing: false }),
    xRunState: vi.fn().mockResolvedValue({ phase: 'idle', postCount: 0, memoryCount: 0 }),
    onXProgress: vi.fn().mockReturnValue(() => {})
  }
})

afterEach(cleanup)

function renderPanel(onDismiss = vi.fn()): { onDismiss: ReturnType<typeof vi.fn> } {
  render(
    <MemoryRouter initialEntries={['/home']}>
      <Routes>
        <Route path="/home" element={<ConnectionsPanel onDismiss={onDismiss} />} />
        <Route path="/apps" element={<div>APPS MARKETPLACE PAGE</div>} />
      </Routes>
    </MemoryRouter>
  )
  return { onDismiss }
}

describe('ConnectionsPanel tray (top level)', () => {
  it('renders the two-column source→destination tray', () => {
    renderPanel()
    // Column headers.
    expect(screen.getByText('Connect data')).toBeTruthy()
    expect(screen.getByText('Use omi memory anywhere')).toBeTruthy()
    // Left (sources) + right (destinations) tiles.
    for (const tile of [
      'tray-tile-gmail',
      'tray-tile-calendar',
      'tray-tile-sticky-notes',
      'tray-tile-x-twitter',
      'tray-tile-omi-device',
      'tray-tile-more-imports',
      'tray-tile-ask-omi',
      'tray-tile-openclaw',
      'tray-tile-hermes',
      'tray-tile-more-exports'
    ]) {
      expect(screen.getByTestId(tile)).toBeTruthy()
    }
    expect(screen.getByText('Claude / Claude Code')).toBeTruthy()
    expect(screen.getByText('ChatGPT / Codex')).toBeTruthy()
  })

  it('drills into a source connector and returns via Back', async () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-gmail'))
    // The Gmail connector detail (renders the "Email" row) is now shown.
    await waitFor(() => expect(screen.getByText('Email')).toBeTruthy())
    expect(screen.getByTestId('connections-back')).toBeTruthy()
    // Back returns to the tray.
    fireEvent.click(screen.getByTestId('connections-back'))
    expect(screen.getByText('Connect data')).toBeTruthy()
  })

  it('drills into the X connector detail', async () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-x-twitter'))
    await waitFor(() => expect(screen.getByText('X (Twitter)')).toBeTruthy())
    expect(screen.getByTestId('connections-back')).toBeTruthy()
  })

  it('opens the full Imports list from the left "+ More"', async () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-more-imports'))
    await waitFor(() => expect(screen.getByText('Imports')).toBeTruthy())
    for (const title of ['Calendar', 'Email', 'Sticky Notes', 'X (Twitter)', 'ChatGPT', 'Claude']) {
      expect(screen.getByText(title)).toBeTruthy()
    }
  })

  it('opens the Exports list from the right "+ More"', async () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-more-exports'))
    await waitFor(() => expect(screen.getByText('Exports')).toBeTruthy())
    for (const title of ['Notion', 'Obsidian', 'Markdown file']) {
      expect(screen.getByText(title)).toBeTruthy()
    }
  })

  it('drills the right-column Claude tile into its export connector detail', async () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-claude-claude-code'))
    // The Claude / Claude Code destination detail (with the Claude Code
    // config-write connector row) is shown, with a Back affordance.
    await waitFor(() => expect(screen.getByTestId('connections-back')).toBeTruthy())
    expect(screen.getByTestId('connector-claude-claude-code')).toBeTruthy()
  })

  it('drills OpenClaw into its export connector detail (no dead "coming soon")', async () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-openclaw'))
    await waitFor(() => expect(screen.getByTestId('connections-back')).toBeTruthy())
    expect(screen.getByTestId('connector-openclaw')).toBeTruthy()
  })

  it('opens the omi.me device page (no drill-in) for Omi Device', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-omi-device'))
    expect(openExternalUrl).toHaveBeenCalledWith('https://www.omi.me')
  })

  it('dismisses the stage when Ask Omi is picked', () => {
    const { onDismiss } = renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-ask-omi'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('dismisses the stage from the tray close button', () => {
    const { onDismiss } = renderPanel()
    fireEvent.click(screen.getByTestId('connect-tray-close'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('navigates to the App Marketplace from the Imports list', async () => {
    const { onDismiss } = renderPanel()
    fireEvent.click(screen.getByTestId('tray-tile-more-imports'))
    await waitFor(() => expect(screen.getByText('Imports')).toBeTruthy())
    fireEvent.click(screen.getByTestId('connector-browse-the-app-marketplace'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByText('APPS MARKETPLACE PAGE')).toBeTruthy())
  })
})

describe('Connect-stage registration', () => {
  it('registers a (lazy) Connect content component on import of register.ts', async () => {
    // main.tsx imports this tiny module for effect; it registers a React.lazy
    // factory so the connections graph loads only when Connect first opens.
    await import('./register')
    expect(getHubConnectContent()).not.toBeNull()
  })
})
