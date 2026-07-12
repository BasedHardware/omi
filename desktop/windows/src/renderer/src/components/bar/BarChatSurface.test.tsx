// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
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

  it('list: every row leads with a status-dot column so all titles share one left margin', () => {
    // Regression for the ragged-left defect: the Omi Chat row used to have no
    // leading column while agent rows led with a dot, so the titles didn't line
    // up. Assert every row's FIRST child is the status dot (same column slot).
    renderSurface({
      view: 'list',
      agents: [{ id: 'acp', displayName: 'Claude Code', working: true }]
    })
    const rows = screen.getAllByRole('button')
    expect(rows.length).toBe(2) // Omi Chat + one agent
    for (const row of rows) {
      const dot = row.querySelector('span.rounded-full')
      expect(dot).toBeTruthy()
      expect(row.firstElementChild).toBe(dot) // leading column, before the title
    }
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

  it('the entering conversation carries NO enter-animation class — it is opaque, seated, from frame 1 (clip-reveal)', () => {
    // Regression for the list→conversation open. The conversation must render fully
    // opaque at its final layout with no opacity/transform animation: an opacity
    // hold reads as a black flash and a transform reads as the page sliding in from
    // above (both user-rejected). The overflow:clip surface reveals it top-down as
    // the box grows. The list keeps bar-view-enter (its quick fade); the
    // conversation must carry neither bar-view-enter nor bar-view-enter-in.
    renderSurface({ view: 'list' })
    expect(document.querySelector('.bar-view-enter')).toBeTruthy()
    cleanup()
    renderSurface({ view: 'conversation' })
    const root = document.querySelector('[data-testid="messages"]')?.closest('.flex.flex-col')
    expect(root).toBeTruthy()
    expect(root?.className).not.toMatch(/bar-view-enter/)
  })

  it('the surface is overflow:clip, never a scroll container (encodes the clip-reveal mechanism)', () => {
    // The mechanism: a tall conversation mounting into the still-small box overflows
    // it. With overflow:hidden the surface is a SCROLL container, so the browser
    // scroll-anchors it (scrollTop>0) and unwinds to 0 as the box grows — sliding
    // the whole conversation down from above (the reported "page drops in from the
    // top"). overflow:clip clips identically but is NOT scrollable, so the content
    // stays seated and the box reveals it top-down. If this regresses to hidden/
    // auto/scroll the slide returns — so pin clip.
    const css = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), 'bar.css'), 'utf8')
    const body = css.match(/\.bar-surface\s*\{([^}]*)\}/)?.[1] ?? ''
    const overflow = body.match(/(?:^|[^-])overflow:\s*([a-z]+)/)?.[1]
    expect(overflow).toBe('clip')
  })
})
