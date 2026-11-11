// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AgentsTab } from './AgentsTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import { __resetClaudeSignIn, onClaudeSignIn } from '../../../lib/claudeSignIn'

// SettingRow reads the settings-search context; provide it so the tab mounts.
const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <AgentsTab />
    </SettingsSearchProvider>
  )
}

// The tab drives the real ACP bridge over window.omi: codingAgentList (external
// agents) + codingAgentAuthStatus (Claude Code sign-in) + codingAgentDetect (CLI
// PATH detection) + codingAgentCodexKeyStatus on mount, codingAgentTest on
// "Test"/"Connect", codingAgentStartAuth/SignOut on the sign-in buttons,
// codingAgentSetCodexKey on the Codex key Save, and onCodingAgentEvent for
// mid-task auth signals. Stub them all — hermetic render test of the Settings →
// Agents surface, no subprocess/network.
const codingAgentList = vi.fn()
const codingAgentTest = vi.fn()
const codingAgentAuthStatus = vi.fn()
const codingAgentStartAuth = vi.fn()
const codingAgentSignOut = vi.fn()
const codingAgentDetect = vi.fn()
const codingAgentCodexKeyStatus = vi.fn()
const codingAgentSetCodexKey = vi.fn()
const onCodingAgentEvent = vi.fn(() => () => {})

const allNotInstalled = {
  codex: { installed: false },
  hermes: { installed: false },
  openclaw: { installed: false }
}

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
  codingAgentDetect.mockReset().mockResolvedValue(allNotInstalled)
  codingAgentCodexKeyStatus.mockReset().mockResolvedValue({ hasKey: false })
  codingAgentSetCodexKey.mockReset().mockResolvedValue({ ok: true, hasKey: true })
  onCodingAgentEvent.mockReset().mockReturnValue(() => {})
  __resetClaudeSignIn()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    codingAgentList,
    codingAgentTest,
    codingAgentAuthStatus,
    codingAgentStartAuth,
    codingAgentSignOut,
    codingAgentDetect,
    codingAgentCodexKeyStatus,
    codingAgentSetCodexKey,
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
    expect(codingAgentDetect).toHaveBeenCalled()
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

  it('shows a Sign in button when Claude Code is signed out, and starts OAuth directly (no upsell sheet) on click', async () => {
    codingAgentAuthStatus.mockResolvedValue({ connected: false, expiresAt: null })
    // The sign-in button must NOT open the "Upgrade to Omi Pro" sheet — connecting
    // the coding agent is plain OAuth, so a Pro user is never paywalled. Watch the
    // shared sheet channel: it must stay closed while sign-in runs.
    let sheetOpened = false
    const unsub = onClaudeSignIn((s) => {
      if (s.open) sheetOpened = true
    })
    renderTab()
    const signIn = await screen.findByText('Sign in to Claude')
    // No handshake Test is offered while signed out (externals show Connect, not Test).
    expect(screen.queryByText('Test')).toBeNull()
    fireEvent.click(signIn)
    await waitFor(() => expect(codingAgentStartAuth).toHaveBeenCalled())
    expect(sheetOpened).toBe(false)
    unsub()
  })

  it('signs out when Disconnect is clicked', async () => {
    renderTab()
    // Only Claude Code is connected here, so its Disconnect is the only one.
    const disconnect = await screen.findByText('Disconnect')
    fireEvent.click(disconnect)
    await waitFor(() => expect(codingAgentSignOut).toHaveBeenCalled())
  })

  it('auto-detects an installed CLI and shows its version instead of install help', async () => {
    codingAgentDetect.mockResolvedValue({
      ...allNotInstalled,
      openclaw: { installed: true, version: '1.2.3', path: 'C:\\bin\\openclaw.cmd' }
    })
    renderTab()
    await waitFor(() => expect(screen.getByText(/CLI installed · v1\.2\.3/)).toBeTruthy())
    // Install guidance for OpenClaw is gone once it's detected.
    expect(screen.queryByText('Install OpenClaw')).toBeNull()
  })

  it('one-click Connect fills the known launch command, saves it, and runs the handshake', async () => {
    renderTab()
    // Externals are unconnected → each shows a Connect button (order: openclaw,
    // hermes, codex). Click OpenClaw's.
    const connects = await screen.findAllByText('Connect')
    fireEvent.click(connects[0])
    await waitFor(() => expect(codingAgentTest).toHaveBeenCalled())
    const [id, overrides] = codingAgentTest.mock.calls[0]
    expect(id).toBe('openclaw')
    expect(overrides.openclaw).toBe('openclaw acp')
  })

  it('validates and stores the Codex OpenAI API key', async () => {
    renderTab()
    const input = await screen.findByPlaceholderText('sk-…')
    fireEvent.change(input, { target: { value: 'sk-test-key' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(codingAgentSetCodexKey).toHaveBeenCalledWith('sk-test-key'))
    await waitFor(() => expect(screen.getByText(/saved and verified/)).toBeTruthy())
  })
})
