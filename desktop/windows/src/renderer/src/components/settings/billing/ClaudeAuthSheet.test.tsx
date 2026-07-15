// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { ClaudeAuthSheet } from './ClaudeAuthSheet'
import { beginClaudeSignIn, __resetClaudeSignIn } from '../../../lib/claudeSignIn'

const codingAgentStartAuth = vi.fn()
const openExternalUrl = vi.fn()

beforeEach(() => {
  codingAgentStartAuth.mockReset().mockReturnValue(new Promise(() => {})) // stays pending → sheet stays open
  openExternalUrl.mockReset().mockResolvedValue(true)
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    codingAgentStartAuth,
    openExternalUrl
  }
  __resetClaudeSignIn()
})

afterEach(() => {
  cleanup()
  __resetClaudeSignIn()
})

describe('ClaudeAuthSheet', () => {
  it('is hidden until a sign-in begins, then shows the Omi Pro upsell copy', async () => {
    render(<ClaudeAuthSheet />)
    expect(screen.queryByText('Upgrade to Omi Pro')).toBeNull()

    beginClaudeSignIn()

    await waitFor(() => expect(screen.getByText('Unlock Omi Pro for $199/month')).toBeTruthy())
    expect(screen.getByText(/Complete sign-in in your browser/)).toBeTruthy()
    // Title + primary CTA both read "Upgrade to Omi Pro".
    expect(screen.getAllByText('Upgrade to Omi Pro').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Cancel')).toBeTruthy()
  })

  it('Upgrade opens omi.me/pricing and closes the sheet', async () => {
    render(<ClaudeAuthSheet />)
    beginClaudeSignIn()
    await waitFor(() => expect(screen.getByText('Unlock Omi Pro for $199/month')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Upgrade to Omi Pro' }))

    expect(openExternalUrl).toHaveBeenCalledWith('https://omi.me/pricing')
    await waitFor(() => expect(screen.queryByText('Unlock Omi Pro for $199/month')).toBeNull())
  })

  it('Cancel closes the sheet without opening a URL', async () => {
    render(<ClaudeAuthSheet />)
    beginClaudeSignIn()
    await waitFor(() => expect(screen.getByText('Unlock Omi Pro for $199/month')).toBeTruthy())

    fireEvent.click(screen.getByText('Cancel'))

    expect(openExternalUrl).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.queryByText('Unlock Omi Pro for $199/month')).toBeNull())
  })

  it('auto-closes when the parallel OAuth completes (granted bypass)', async () => {
    let resolveAuth!: (v: unknown) => void
    codingAgentStartAuth.mockReturnValue(new Promise((res) => (resolveAuth = res)))
    render(<ClaudeAuthSheet />)
    beginClaudeSignIn()
    await waitFor(() => expect(screen.getByText('Unlock Omi Pro for $199/month')).toBeTruthy())

    resolveAuth({ ok: true, status: { connected: true, expiresAt: 1 } })

    await waitFor(() => expect(screen.queryByText('Unlock Omi Pro for $199/month')).toBeNull())
  })
})
