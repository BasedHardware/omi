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

// The tab drives the real ACP bridge over window.omi: codingAgentList (external
// agents) + codingAgentAuthStatus (Claude Code sign-in) on mount, codingAgentTest
// on "Test", codingAgentStartAuth/SignOut on the sign-in buttons, and
// onCodingAgentEvent for mid-task auth signals. Stub them all — hermetic render
// test of the Settings → Agents surface, no subprocess/network.
const codingAgentList = vi.fn()
const codingAgentTest = vi.fn()
const codingAgentAuthStatus = vi.fn()
const codingAgentStartAuth = vi.fn()
const codingAgentSignOut = vi.fn()
const onCodingAgentEvent = vi.fn(() => () => {})

beforeEach(() => {
  localStorage.clear()
  codingAgentList.mockReset().mockResolvedValue([
    { id: 'acp', displayName: 'Claude Code', connected: true },
    { id: 'openclaw', displayName: 'OpenClaw', connected: false, installHint: 'command not found' },
    { id: 'hermes', displayName: 'Hermes', connected: false },
    { id: 'codex', displayName: 'Codex', connected: false }
  ])
  codingAgentTest.mockReset().mockResolvedValue({ ok: true })
  codingAgentAuthStatus.mockReset().mockResolvedValue({ connected: true, expiresAt: null })
  codingAgentStartAuth
    .mockReset()
    .mockResolvedValue({ ok: true, status: { connected: true, expiresAt: null } })
  codingAgentSignOut.mockReset().mockResolvedValue({ connected: false, expiresAt: null })
  onCodingAgentEvent.mockReset().mockReturnValue(() => {})
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    codingAgentList,
    codingAgentTest,
    codingAgentAuthStatus,
    codingAgentStartAuth,
    codingAgentSignOut,
    onCodingAgentEvent
  }
})

afterEach(cleanup)

describe('AgentsTab', () => {
  it('lists the built-in Claude Code agent plus the external agents, with install help for the unconnected', async () => {
    renderTab()
    expect(screen.getByText('Claude Code')).toBeTruthy()
    // Signed in → the row reflects the connected account.
    await waitFor(() => expect(screen.getByText(/signed in with your Claude account/)).toBeTruthy())
    // Externals resolve from the bridge; an unconnected one shows install guidance.
    await waitFor(() => expect(screen.getByText('Install OpenClaw')).toBeTruthy())
    expect(screen.getByText('Hermes')).toBeTruthy()
    expect(screen.getByText('Codex')).toBeTruthy()
    expect(codingAgentList).toHaveBeenCalled()
    expect(codingAgentAuthStatus).toHaveBeenCalled()
  })

  it('runs a real ACP handshake when Test is clicked on the signed-in built-in agent', async () => {
    renderTab()
    // Test + Disconnect render only once Claude Code is signed in.
    await waitFor(() => expect(screen.getByText('Test')).toBeTruthy())
    fireEvent.click(screen.getByText('Test'))
    await waitFor(() => expect(codingAgentTest).toHaveBeenCalled())
    expect(codingAgentTest.mock.calls[0][0]).toBe('acp')
    await waitFor(() => expect(screen.getByText(/answered the handshake/)).toBeTruthy())
  })

  it('shows a Sign in button when Claude Code is signed out, and starts the flow on click', async () => {
    codingAgentAuthStatus.mockResolvedValue({ connected: false, expiresAt: null })
    renderTab()
    const signIn = await screen.findByText('Sign in to Claude')
    // No handshake Test is offered while signed out.
    expect(screen.queryByText('Test')).toBeNull()
    fireEvent.click(signIn)
    await waitFor(() => expect(codingAgentStartAuth).toHaveBeenCalled())
  })

  it('signs out when Disconnect is clicked', async () => {
    renderTab()
    const disconnect = await screen.findByText('Disconnect')
    fireEvent.click(disconnect)
    await waitFor(() => expect(codingAgentSignOut).toHaveBeenCalled())
  })
})
