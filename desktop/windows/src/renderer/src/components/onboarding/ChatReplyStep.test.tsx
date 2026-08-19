// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor, act } from '@testing-library/react'
import { ChatReplyStep } from './ChatReplyStep'
import type { BeeperStatus } from '../../../../shared/types'

const beeperStatus = vi.fn()
const beeperConnect = vi.fn()
const beeperSetSettings = vi.fn()
const beeperOpenDownload = vi.fn()

const idle: BeeperStatus = {
  running: false,
  connected: false,
  enabled: false,
  sendMode: 'draft',
  networks: ['whatsapp', 'telegram'],
  accounts: [],
  draftCount: 0,
  imessageSupported: false
}

beforeEach(() => {
  beeperStatus.mockReset().mockResolvedValue(idle)
  beeperConnect.mockReset().mockResolvedValue({ ...idle, running: true, connected: true })
  beeperSetSettings.mockReset().mockResolvedValue({ ...idle, connected: true, enabled: true })
  beeperOpenDownload.mockReset()
  ;(window as unknown as { omi: unknown }).omi = {
    beeperStatus,
    beeperConnect,
    beeperSetSettings,
    beeperOpenDownload
  }
})

afterEach(cleanup)

describe('ChatReplyStep', () => {
  it('shows the reply demo without requiring Beeper', async () => {
    render(<ChatReplyStep stepIndex={13} totalSteps={15} onContinue={vi.fn()} onSkip={vi.fn()} />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByTestId('chat-reply-demo')).toBeTruthy()
    expect(screen.getByText(/what time does your flight land/)).toBeTruthy()
    expect(screen.getByText(/6:40pm/)).toBeTruthy()
  })

  it('lets the user skip without connecting', async () => {
    const onSkip = vi.fn()
    render(<ChatReplyStep stepIndex={13} totalSteps={15} onContinue={vi.fn()} onSkip={onSkip} />)
    await waitFor(() => expect(beeperStatus).toHaveBeenCalled())
    fireEvent.click(screen.getByText('Skip'))
    expect(onSkip).toHaveBeenCalledTimes(1)
    expect(beeperSetSettings).not.toHaveBeenCalled()
  })

  it('offers Install Beeper when Desktop is not running', async () => {
    render(<ChatReplyStep stepIndex={13} totalSteps={15} onContinue={vi.fn()} onSkip={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Install Beeper')).toBeTruthy())
    fireEvent.click(screen.getByText('Install Beeper'))
    expect(beeperOpenDownload).toHaveBeenCalledTimes(1)
  })

  it('connects a pasted token and enables drafts on Continue', async () => {
    const onContinue = vi.fn()
    beeperStatus.mockResolvedValue({ ...idle, running: true })
    render(
      <ChatReplyStep stepIndex={13} totalSteps={15} onContinue={onContinue} onSkip={vi.fn()} />
    )
    const input = await screen.findByPlaceholderText('Paste access token')
    fireEvent.change(input, { target: { value: 'tok_test' } })
    fireEvent.click(screen.getByText('Connect'))
    await waitFor(() => expect(beeperConnect).toHaveBeenCalledWith('tok_test'))
    fireEvent.click(screen.getByText('Enable drafts'))
    await waitFor(() =>
      expect(beeperSetSettings).toHaveBeenCalledWith({
        enabled: true,
        sendMode: 'draft',
        networks: ['whatsapp', 'telegram']
      })
    )
    expect(onContinue).toHaveBeenCalledTimes(1)
  })
})
