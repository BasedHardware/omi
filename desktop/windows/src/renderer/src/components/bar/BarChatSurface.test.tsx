// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { BarChatSurface, type BarChatSurfaceProps } from './BarChatSurface'
import type { BarChatState } from '../../../../shared/types'

// The conversation view pins the message list with a ResizeObserver (absent in jsdom).
/* eslint-disable @typescript-eslint/no-empty-function -- no-op ResizeObserver stub */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

// The message list is markdown-heavy and tested elsewhere; stub it so this test
// focuses on the list ⇄ conversation navigation + send wiring.
vi.mock('../chat/ChatMessages', () => ({
  ChatMessages: ({ messages }: { messages: unknown[] }) => (
    <div data-testid="messages">{messages.length}</div>
  )
}))

const baseChat: BarChatState = {
  messages: [{ id: 'a1', role: 'assistant', content: 'Here is the answer' }],
  sending: false,
  status: 'idle'
}

function renderSurface(overrides: Partial<BarChatSurfaceProps> = {}): BarChatSurfaceProps {
  const props: BarChatSurfaceProps = {
    chat: baseChat,
    agents: [],
    view: 'list',
    onOpenConversation: vi.fn(),
    onBack: vi.fn(),
    onClose: vi.fn(),
    draft: '',
    setDraft: vi.fn(),
    onSubmit: vi.fn(),
    pttKeyDown: vi.fn(() => false),
    pttKeyUp: vi.fn(() => false),
    recording: false,
    transcribing: false,
    maxListHeight: 300,
    ...overrides
  }
  render(<BarChatSurface {...props} />)
  return props
}

afterEach(() => cleanup())

describe('BarChatSurface', () => {
  it('list: shows the Omi Chat row and opens the conversation on click', () => {
    const props = renderSurface({ view: 'list' })
    expect(screen.getByText('Omi Chat')).toBeTruthy()
    // The row previews the last turn.
    expect(screen.getByText('Here is the answer')).toBeTruthy()
    fireEvent.click(screen.getByText('Omi Chat'))
    expect(props.onOpenConversation).toHaveBeenCalledTimes(1)
  })

  it('list: renders a row per connected agent and opens the shared conversation on click', () => {
    const props = renderSurface({
      view: 'list',
      agents: [
        { id: 'acp', displayName: 'Claude Code', working: false },
        { id: 'codex', displayName: 'Codex', working: true }
      ]
    })
    expect(screen.getByText('Claude Code')).toBeTruthy()
    expect(screen.getByText('Ready')).toBeTruthy()
    // The running agent shows its live status.
    expect(screen.getByText('Codex')).toBeTruthy()
    expect(screen.getByText('Working…')).toBeTruthy()
    // A row opens the SAME inline conversation as Omi Chat (shared thread).
    fireEvent.click(screen.getByText('Claude Code'))
    expect(props.onOpenConversation).toHaveBeenCalledTimes(1)
  })

  it('conversation: renders the thread and the back chevron returns to the list', () => {
    const props = renderSurface({ view: 'conversation' })
    expect(screen.getByTestId('messages').textContent).toBe('1')
    fireEvent.click(screen.getByLabelText('Back to list'))
    expect(props.onBack).toHaveBeenCalledTimes(1)
  })

  it('conversation: typed input keeps the input and Enter sends a NON-voice turn', () => {
    const props = renderSurface({ view: 'conversation', draft: 'hello there' })
    const input = screen.getByPlaceholderText(/Ask Omi/i)
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(props.onSubmit).toHaveBeenCalledWith('hello there')
    expect(props.setDraft).toHaveBeenCalledWith('')
  })

  it('conversation: an empty thread invites instead of dead-ending', () => {
    renderSurface({ view: 'conversation', chat: { messages: [], sending: false, status: 'idle' } })
    expect(screen.getByText(/Ask Omi anything/i)).toBeTruthy()
  })

  it('conversation: the close control fires onClose', () => {
    const props = renderSurface({ view: 'conversation' })
    fireEvent.click(screen.getByLabelText('Close'))
    expect(props.onClose).toHaveBeenCalledTimes(1)
  })
})
