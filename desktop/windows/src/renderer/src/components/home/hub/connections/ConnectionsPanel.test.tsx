// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// useMemories + the Calendar status probe fetch on mount; keep them offline.
const { omiGet } = vi.hoisted(() => ({ omiGet: vi.fn() }))
vi.mock('../../../../lib/apiClient', () => ({
  omiApi: { get: omiGet, post: vi.fn(), delete: vi.fn() },
  desktopApi: { post: vi.fn() }
}))

import { ConnectionsPanel } from './ConnectionsPanel'
import { getHubConnectContent } from '../hubConnectSlot'

beforeEach(() => {
  // One mock for every GET: useMemories reads .memories, the Calendar probe reads
  // .connected — both fall out to empty/false, which every card renders fine.
  omiGet.mockResolvedValue({ data: { memories: [], connected: false } })
  ;(window as unknown as { omi: Record<string, unknown> }).omi = {
    openExternalUrl: vi.fn(),
    readStickyNotes: vi.fn()
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

describe('ConnectionsPanel', () => {
  it('renders the Imports and Exports sections with their connector rows, in Mac order', async () => {
    renderPanel()
    expect(screen.getByText('Imports')).toBeTruthy()
    expect(screen.getByText('Exports')).toBeTruthy()
    for (const title of [
      'Calendar',
      'Email',
      'Sticky Notes',
      'ChatGPT',
      'Claude',
      'Notion',
      'Obsidian',
      'Markdown file'
    ]) {
      expect(screen.getByText(title)).toBeTruthy()
    }
  })

  it('navigates to the App Marketplace and dismisses when the link is clicked', async () => {
    const { onDismiss } = renderPanel()
    fireEvent.click(screen.getByTestId('connections-apps-link'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByText('APPS MARKETPLACE PAGE')).toBeTruthy())
  })

  it('shows the Email card in a non-dead "requires configuration" state when the client lane is unconfigured', () => {
    renderPanel()
    expect(screen.getByText(/Requires Google sign-in to be configured/)).toBeTruthy()
  })
})

describe('Connect-stage registration', () => {
  it('registers ConnectionsPanel as the Hub Connect content on import', () => {
    // Importing the panel module (top of this file) runs its bottom-of-file
    // registerHubConnectContent side effect — the same seam main.tsx triggers.
    expect(getHubConnectContent()).toBe(ConnectionsPanel)
  })
})
