// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AiCloneTab } from './AiCloneTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <AiCloneTab />
    </SettingsSearchProvider>
  )
}

const aiCloneConnect = vi.fn()
const aiCloneStatus = vi.fn()
const aiCloneDisconnect = vi.fn()
const aiCloneListChats = vi.fn()
const aiCloneSetChatMode = vi.fn()
const aiCloneListDrafts = vi.fn()
const aiCloneApproveDraft = vi.fn()
const aiCloneDismissDraft = vi.fn()

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  aiCloneStatus.mockReset().mockResolvedValue({ connected: false, accounts: [] })
  aiCloneConnect.mockReset()
  aiCloneDisconnect.mockReset().mockResolvedValue(undefined)
  aiCloneListChats.mockReset().mockResolvedValue([])
  aiCloneSetChatMode.mockReset().mockResolvedValue(undefined)
  aiCloneListDrafts.mockReset().mockResolvedValue([])
  aiCloneApproveDraft.mockReset().mockResolvedValue(undefined)
  aiCloneDismissDraft.mockReset().mockResolvedValue(undefined)
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    aiCloneConnect,
    aiCloneStatus,
    aiCloneDisconnect,
    aiCloneListChats,
    aiCloneSetChatMode,
    aiCloneListDrafts,
    aiCloneApproveDraft,
    aiCloneDismissDraft
  }
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('AiCloneTab', () => {
  it('shows the connect flow when not connected', async () => {
    renderTab()
    await waitFor(() => expect(aiCloneStatus).toHaveBeenCalled())
    expect(screen.getByPlaceholderText('Beeper access token')).toBeTruthy()
    expect(screen.getByText('Connect')).toBeTruthy()
  })

  it('connects with the pasted token and surfaces the resulting accounts', async () => {
    aiCloneConnect.mockResolvedValue({
      connected: true,
      accounts: [{ accountID: 'a1', network: 'WhatsApp', displayName: 'Me' }]
    })
    aiCloneStatus.mockResolvedValueOnce({ connected: false, accounts: [] }).mockResolvedValue({
      connected: true,
      accounts: [{ accountID: 'a1', network: 'WhatsApp', displayName: 'Me' }]
    })
    renderTab()
    const input = await screen.findByPlaceholderText('Beeper access token')
    fireEvent.change(input, { target: { value: 'secret-token' } })
    fireEvent.click(screen.getByText('Connect'))
    await waitFor(() => expect(aiCloneConnect).toHaveBeenCalledWith('secret-token'))
    await waitFor(() => expect(screen.getByText(/Connected — WhatsApp/)).toBeTruthy())
  })

  it('shows a connect error without storing anything', async () => {
    aiCloneConnect.mockResolvedValue({
      connected: false,
      accounts: [],
      error: 'Beeper Desktop is not running.'
    })
    renderTab()
    const input = await screen.findByPlaceholderText('Beeper access token')
    fireEvent.change(input, { target: { value: 'bad-token' } })
    fireEvent.click(screen.getByText('Connect'))
    await waitFor(() => expect(screen.getByText('Beeper Desktop is not running.')).toBeTruthy())
    // Still shows the connect form — never silently treats a failed connect as success.
    expect(screen.getByPlaceholderText('Beeper access token')).toBeTruthy()
  })

  it('lists chats with a mode selector once connected, and saves a mode change', async () => {
    aiCloneStatus.mockResolvedValue({ connected: true, accounts: [] })
    aiCloneListChats.mockResolvedValue([
      { chatID: 'c1', displayName: 'Alex', network: 'WhatsApp', type: 'single', mode: 'off' }
    ])
    renderTab()
    await waitFor(() => expect(screen.getByText('Alex')).toBeTruthy())
    const select = screen.getByDisplayValue('Off') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'draft' } })
    await waitFor(() => expect(aiCloneSetChatMode).toHaveBeenCalledWith('c1', 'Alex', 'draft'))
  })

  it('shows queued drafts and sends one on approve', async () => {
    aiCloneListDrafts.mockResolvedValue([
      {
        id: 'd1',
        chatID: 'c1',
        chatDisplayName: 'Alex',
        incomingMessageText: 'are we on for 6?',
        draftText: 'yep, see you then!',
        createdAt: Date.now()
      }
    ])
    renderTab()
    await waitFor(() => expect(screen.getByText('Drafted replies')).toBeTruthy())
    expect(screen.getByDisplayValue('yep, see you then!')).toBeTruthy()
    fireEvent.click(screen.getByText('Send'))
    await waitFor(() => expect(aiCloneApproveDraft).toHaveBeenCalledWith('d1', undefined))
  })

  it('dismisses a draft without sending it', async () => {
    aiCloneListDrafts.mockResolvedValue([
      {
        id: 'd1',
        chatID: 'c1',
        chatDisplayName: 'Alex',
        incomingMessageText: 'are we on for 6?',
        draftText: 'yep, see you then!',
        createdAt: Date.now()
      }
    ])
    renderTab()
    await waitFor(() => expect(screen.getByText('Dismiss')).toBeTruthy())
    fireEvent.click(screen.getByText('Dismiss'))
    await waitFor(() => expect(aiCloneDismissDraft).toHaveBeenCalledWith('d1'))
    expect(aiCloneApproveDraft).not.toHaveBeenCalled()
  })

  it('disconnects and clears the chat list', async () => {
    aiCloneStatus
      .mockResolvedValueOnce({ connected: true, accounts: [] })
      .mockResolvedValue({ connected: false, accounts: [] })
    renderTab()
    const disconnect = await screen.findByText('Disconnect')
    fireEvent.click(disconnect)
    await waitFor(() => expect(aiCloneDisconnect).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByPlaceholderText('Beeper access token')).toBeTruthy())
  })
})
