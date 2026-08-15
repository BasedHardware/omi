// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import type { ActionItemRecord } from '../../../../shared/types'
import type { TaskChatMessage } from '../../lib/taskChat'

// The panel is tested around a mocked send: what matters here is the panel
// contract — transcript rendering, the sending state, the honest failure path
// with retry, and clear — not the prompt/LLM plumbing (lib/taskChat owns that).
const sendMock = vi.fn()
const loadMock = vi.fn()
const clearMock = vi.fn()
vi.mock('../../lib/taskChat', () => ({
  loadTaskChat: (...args: unknown[]) => loadMock(...args),
  saveTaskChat: vi.fn(),
  clearTaskChat: (...args: unknown[]) => clearMock(...args),
  sendTaskChatMessage: (...args: unknown[]) => sendMock(...args)
}))

import { TaskChatPanel } from './TaskChatPanel'

const task = (over: Partial<ActionItemRecord> = {}): ActionItemRecord =>
  ({
    id: 1,
    backendId: 'b-1',
    description: 'Investigate the failing build',
    completed: false,
    tags: [],
    createdAt: 1,
    updatedAt: 1,
    ...over
  }) as ActionItemRecord

const msg = (role: 'user' | 'assistant', content: string): TaskChatMessage => ({
  role,
  content,
  at: 1
})

beforeEach(() => {
  loadMock.mockReturnValue([])
  sendMock.mockReset()
  clearMock.mockReset()
  ;(Element.prototype as unknown as { scrollTo: () => void }).scrollTo = vi.fn()
})

afterEach(() => {
  cleanup()
})

describe('TaskChatPanel', () => {
  it('loads the persisted transcript for the task', () => {
    loadMock.mockReturnValue([msg('user', 'earlier question'), msg('assistant', 'earlier answer')])
    render(<TaskChatPanel task={task()} onClose={() => {}} />)
    expect(loadMock).toHaveBeenCalledWith('b-1')
    expect(screen.getByText('earlier question')).not.toBeNull()
    expect(screen.getByText('earlier answer')).not.toBeNull()
  })

  it('sends on Enter, shows the user turn immediately, then the reply', async () => {
    let resolveSend: (v: TaskChatMessage[]) => void = () => {}
    sendMock.mockReturnValue(
      new Promise<TaskChatMessage[]>((r) => {
        resolveSend = r
      })
    )
    render(<TaskChatPanel task={task()} onClose={() => {}} />)

    const input = screen.getByTestId('task-chat-input')
    fireEvent.change(input, { target: { value: 'what next?' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // Optimistic user turn + thinking indicator while the send is in flight.
    expect(screen.getByText('what next?')).not.toBeNull()
    expect(screen.getByText('Thinking…')).not.toBeNull()

    resolveSend([msg('user', 'what next?'), msg('assistant', 'try X')])
    await waitFor(() => expect(screen.queryByText('try X')).not.toBeNull())
    expect(screen.queryByText('Thinking…')).toBeNull()
  })

  it('keeps the user turn and offers retry when the send fails', async () => {
    sendMock.mockRejectedValueOnce(new Error('down'))
    render(<TaskChatPanel task={task()} onClose={() => {}} />)

    const input = screen.getByTestId('task-chat-input')
    fireEvent.change(input, { target: { value: 'help' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(screen.queryByTestId('task-chat-retry')).not.toBeNull())
    expect(screen.getByText('help')).not.toBeNull()

    sendMock.mockResolvedValueOnce([msg('user', 'help'), msg('assistant', 'recovered')])
    fireEvent.click(screen.getByTestId('task-chat-retry'))
    await waitFor(() => expect(screen.queryByText('recovered')).not.toBeNull())
    // The retry re-sends the ORIGINAL turn against its pre-failure history.
    expect(sendMock).toHaveBeenCalledTimes(2)
    expect(sendMock.mock.calls[1][2]).toBe('help')
  })

  it('clears the transcript through the lib', () => {
    loadMock.mockReturnValue([msg('user', 'q'), msg('assistant', 'a')])
    render(<TaskChatPanel task={task()} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('task-chat-clear'))
    expect(clearMock).toHaveBeenCalledWith('b-1')
    expect(screen.queryByText('q')).toBeNull()
  })

  it('close button calls onClose', () => {
    const onClose = vi.fn()
    render(<TaskChatPanel task={task()} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('task-chat-close'))
    expect(onClose).toHaveBeenCalled()
  })
})
