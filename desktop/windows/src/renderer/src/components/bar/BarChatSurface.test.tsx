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

  it('view roots carry the direction-specific morph class (guards the anti-plummet fix)', () => {
    // Regression for the list→conversation "plummet": a tall conversation bottom-
    // pins to the growing surface, so opening it used to slide the whole view down
    // from far above the top edge. The conversation root must use bar-view-enter-in
    // (holds it invisible through that slide, then blooms it in at rest); the list
    // root keeps bar-view-enter (the top-pinned deflate the user likes). If either
    // class is swapped/dropped, the plummet returns — so pin them here.
    renderSurface({ view: 'list' })
    expect(document.querySelector('.bar-view-enter')).toBeTruthy()
    expect(document.querySelector('.bar-view-enter-in')).toBeNull()
    cleanup()
    renderSurface({ view: 'conversation' })
    expect(document.querySelector('.bar-view-enter-in')).toBeTruthy()
  })

  it('bar-view-enter-in holds the conversation invisible until the box is ~seated (encodes the anti-plummet mechanism)', () => {
    // The mechanism, not just the wiring: a tall conversation is bottom-pinned to
    // the surface, so its top sweeps ~460px downward WHILE the box height morph
    // (~240ms) runs. The plummet is masked only because bar-view-enter-in keeps
    // opacity 0 through most of that sweep, then blooms once the box is ~seated.
    // Measured: opacity first exceeds 0 at ~62% of the 300ms curve, when the box
    // is ~90% grown and the view is ~2px from rest. If someone shortens that hold
    // the visible slide returns — so pin it: opacity must stay 0 until >= 55%.
    const css = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), 'bar.css'), 'utf8')
    const block = css.match(/@keyframes\s+bar-view-enter-in\s*\{([\s\S]*?)\n\}/)?.[1]
    expect(block).toBeTruthy()
    let holdUntilPct = 0
    let blooms = false
    for (const [, selector, body] of (block as string).matchAll(/([\d%,\s]+?)\{([^}]*)\}/g)) {
      const pcts = [...selector.matchAll(/(\d+)%/g)].map((x) => Number(x[1]))
      if (/opacity:\s*0\b/.test(body)) holdUntilPct = Math.max(holdUntilPct, ...pcts)
      if (pcts.includes(100) && /opacity:\s*1\b/.test(body)) blooms = true
    }
    expect(holdUntilPct).toBeGreaterThanOrEqual(55)
    expect(blooms).toBe(true)
  })
})
