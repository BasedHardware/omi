// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AgentsTab } from './AgentsTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

// SettingRow reads the settings-search context; provide it so the tab mounts.
const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <AgentsTab />
    </SettingsSearchProvider>
  )
}

// The tab drives the real ACP bridge over window.omi on mount (codingAgentList)
// and on "Test" (codingAgentTest). Stub both — this is a hermetic render test of
// the Settings → Agents surface, no subprocess/network.
const codingAgentList = vi.fn()
const codingAgentTest = vi.fn()

beforeEach(() => {
  localStorage.clear()
  codingAgentList.mockReset().mockResolvedValue([
    { id: 'acp', displayName: 'Claude Code', connected: true },
    { id: 'openclaw', displayName: 'OpenClaw', connected: false, installHint: 'command not found' },
    { id: 'hermes', displayName: 'Hermes', connected: false },
    { id: 'codex', displayName: 'Codex', connected: false }
  ])
  codingAgentTest.mockReset().mockResolvedValue({ ok: true })
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    codingAgentList,
    codingAgentTest
  }
})

afterEach(cleanup)

describe('AgentsTab', () => {
  it('lists the built-in Claude Code agent plus the external agents, with install help for the unconnected', async () => {
    renderTab()
    // Built-in — always present; rides the machine's Claude login (no API key).
    expect(screen.getByText('Claude Code')).toBeTruthy()
    expect(screen.getByText(/Signs in with your Claude account/)).toBeTruthy()
    // Externals resolve from the bridge; an unconnected one shows install guidance.
    await waitFor(() => expect(screen.getByText('Install OpenClaw')).toBeTruthy())
    expect(screen.getByText('Hermes')).toBeTruthy()
    expect(screen.getByText('Codex')).toBeTruthy()
    expect(codingAgentList).toHaveBeenCalled()
  })

  it('runs a real ACP handshake when Test is clicked on the connected built-in agent', async () => {
    renderTab()
    // Only connected agents render a Test button; here that is just Claude Code.
    await waitFor(() => expect(screen.getByText('Test')).toBeTruthy())
    fireEvent.click(screen.getByText('Test'))
    await waitFor(() => expect(codingAgentTest).toHaveBeenCalled())
    expect(codingAgentTest.mock.calls[0][0]).toBe('acp')
    await waitFor(() => expect(screen.getByText(/answered the handshake/)).toBeTruthy())
  })
})
