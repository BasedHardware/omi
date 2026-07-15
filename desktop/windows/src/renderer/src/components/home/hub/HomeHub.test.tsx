// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// The Hub drives the app's ONE chat engine — asserted here by checking that a submit
// calls the shared chat.send, not some second message array of its own.

type ChatMsg = { id?: string; role: 'user' | 'assistant'; content: string }
let chat: { history: ChatMsg[]; sending: boolean; send: ReturnType<typeof vi.fn> }
vi.mock('../../../state/appState', () => ({ useAppState: () => ({ chat }) }))

let memories: { memories: { id: string }[]; loading: boolean; error?: string | null }
vi.mock('../../../hooks/useMemories', () => ({ useMemories: () => memories }))

// The stat ribbon's non-memory sources. Tasks reuses the Tasks page's paginating
// fetch; conversations observes the Conversations page's cache.
let actionItems: { id: string }[]
vi.mock('../../../lib/actionItems', () => ({
  fetchAllActionItems: () => Promise.resolve(actionItems)
}))

// The two cluster widgets fetch on mount; stub them out — they are covered by their
// own tests, and this suite is about the Hub.
vi.mock('../QuickTaskWidget', () => ({ QuickTaskWidget: () => <div data-testid="quick-tasks" /> }))
vi.mock('../QuickGoalsWidget', () => ({
  QuickGoalsWidget: () => <div data-testid="quick-goals" />
}))

import { publishConversationsCache, invalidateConversationsCache } from '../../../lib/pageCache'
import type { ConversationRow } from '../../../lib/pageCache'

const convRow = (id: string, source: 'cloud' | 'local'): ConversationRow =>
  ({ id, title: id, subtitle: '', preview: '', source, sortAt: 0 }) as ConversationRow

/* eslint-disable @typescript-eslint/no-empty-function -- no-op stub */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

import { HomeHub } from './HomeHub'

const renderHub = (): void => {
  render(
    <MemoryRouter>
      <HomeHub />
    </MemoryRouter>
  )
}
const stage = (): HTMLElement => screen.getByTestId('hub-stage')
const mode = (): string | null => stage().getAttribute('data-mode')
const askBar = (): HTMLElement => screen.getByLabelText('Ask omi anything')

beforeEach(() => {
  chat = { history: [], sending: false, send: vi.fn() }
  memories = { memories: [{ id: 'm1' }, { id: 'm2' }, { id: 'm3' }], loading: false }
  actionItems = [{ id: 't1' }, { id: 't2' }]
  invalidateConversationsCache()
  // The header reads the real capture settings on mount; the ribbon reads the real
  // rewind frame COUNT (a COUNT(*) in main, not a row fetch).
  ;(window as unknown as { omi: unknown }).omi = {
    rewindGetSettings: vi.fn().mockResolvedValue({ captureEnabled: false }),
    rewindSetSettings: vi.fn().mockResolvedValue({ captureEnabled: true }),
    // The header SUBSCRIBES to main's rewind:settings broadcast so it can't drift
    // out of sync with the sidebar's copy of the same toggle.
    onRewindSettings: vi.fn().mockReturnValue(() => {}),
    rewindFrameCount: vi.fn().mockResolvedValue(1234),
    openExternalUrl: vi.fn()
  }
})
afterEach(cleanup)

describe('HomeHub — stage machine', () => {
  it('rests on the hub, showing the wordmark', () => {
    renderHub()
    expect(mode()).toBe('hub')
    // "omi." — with the period, as on Mac (DashboardPage.swift:738).
    expect(screen.getByText('omi.')).not.toBeNull()
  })

  it('labels the header pills with the FEATURE NAME, not the on/off state', () => {
    // Mac's pills read "Capture" / "Listening" (state is carried by colour), not
    // "On" / "Off" (DashboardPage.swift HomeStatusButton title:). Showing the state
    // as the label read as a bare toggle with no hint of which control it was.
    renderHub()
    expect(screen.getByText('Capture')).not.toBeNull()
    expect(screen.getByText('Listening')).not.toBeNull()
    expect(screen.queryByText('Off')).toBeNull()
  })

  it('docks the cluster with NOTHING between the wordmark and the stat ribbon', () => {
    // Mac's hub stage is wordmark → flexible gap → ribbon → ask bar → suggestions
    // (DashboardPage.swift:678-702). An earlier build wedged two 160px legacy
    // widget cards in above the ribbon, which pushed the ask bar off the bottom of
    // a short window. There is no slot there — keep it empty.
    renderHub()
    const stage = document.querySelector('[data-testid="hub-stage"]') as HTMLElement
    const cluster = stage.querySelector('[data-testid="hub-cluster"]') as HTMLElement
    expect(cluster).not.toBeNull()

    // The stage's only element children are: spacer, wordmark, spacer, cluster.
    // Anything else is a widget that does not exist on Mac.
    const wordmark = stage.querySelector('h1') as HTMLElement
    const kids = [...stage.children]
    expect(kids).toHaveLength(4)
    expect(kids[1]).toBe(wordmark)
    expect(kids[3]).toBe(cluster)

    // And the cluster leads with the ribbon — the ask bar is never pushed down.
    expect(cluster.textContent).toMatch(/Conversations/)
  })

  it('keeps the caret in the ask bar when focusing it opens the chat panel', () => {
    // The bar RE-DOCKS into the panel, so React remounts the input under a new
    // parent. Without an explicit re-focus the caret lands on <body> and the first
    // thing the user types after clicking the bar goes nowhere.
    renderHub()
    fireEvent.focus(askBar())
    expect(mode()).toBe('chat')
    expect(document.activeElement).toBe(askBar())
  })

  it('moves to chat and sends through the SHARED chat engine on submit', () => {
    renderHub()
    fireEvent.change(askBar(), { target: { value: 'hello omi' } })
    fireEvent.keyDown(askBar(), { key: 'Enter' })

    expect(chat.send).toHaveBeenCalledWith('hello omi')
    expect(mode()).toBe('chat')
  })

  it('sends the suggestion text when a suggestion is tapped', () => {
    renderHub()
    const suggestion = screen.getByText('What did I spend my time on this week?')
    fireEvent.click(suggestion)

    expect(chat.send).toHaveBeenCalledWith('What did I spend my time on this week?')
    expect(mode()).toBe('chat')
  })

  it('returns to the hub on Esc', () => {
    renderHub()
    fireEvent.focus(askBar())
    expect(mode()).toBe('chat')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(mode()).toBe('hub')
  })

  it('toggles the connect stage from the ask bar and back', () => {
    renderHub()
    const connect = screen.getByRole('button', { name: 'Connect' })
    fireEvent.click(connect)
    expect(mode()).toBe('connect')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(mode()).toBe('hub')
  })

  it('does not send an empty message', () => {
    renderHub()
    fireEvent.keyDown(askBar(), { key: 'Enter' })
    expect(chat.send).not.toHaveBeenCalled()
  })
})

describe('HubAskBar — no control that cannot do what it looks like it does', () => {
  it('shows a NON-INTERACTIVE busy indicator while sending — never a stop button', () => {
    // A stop button here could only be wired to chat.reset(), which starts a fresh
    // conversation — it would delete the user's thread to halt one reply. Until the
    // chat engine grows a real abort, nothing here may invite a press.
    chat.sending = true
    renderHub()

    const busy = screen.getByRole('status')
    expect(busy.getAttribute('aria-busy')).toBe('true')
    // The guard that matters: no pressable control in the trailing slot.
    expect(screen.queryByRole('button', { name: /stop/i })).toBeNull()
    expect(busy.querySelector('button')).toBeNull()
  })

  it('renders no paperclip — the app has no attachment path to back one', () => {
    renderHub()
    // Not "hidden from screen readers": absent. A visible paperclip invites a click
    // that would do nothing at all.
    expect(document.querySelector('.lucide-paperclip')).toBeNull()
  })
})

describe('HomeHub — stat ribbon counts come from the real sources', () => {
  const cell = (name: RegExp): HTMLElement => screen.getByRole('button', { name })

  it('renders memories from useMemories and tasks from the paginating Tasks fetch', async () => {
    renderHub()
    expect(cell(/Memories/).textContent).toContain('3')
    await waitFor(() => expect(cell(/Tasks/).textContent).toContain('2'))
  })

  it('renders screenshots from the rewind COUNT(*) IPC, not a frame-row length', async () => {
    renderHub()
    await waitFor(() => expect(cell(/Screenshots/).textContent).toContain('1234'))
    expect(window.omi.rewindFrameCount).toHaveBeenCalled()
  })

  it('counts conversations off the Conversations page cache — no second fetch', async () => {
    renderHub()
    publishConversationsCache([convRow('a', 'cloud'), convRow('b', 'local')])
    await waitFor(() => expect(cell(/Conversations/).textContent).toContain('2'))
  })

  it('renders a FULL cloud page as "100+" — never a page length dressed as a total', async () => {
    renderHub()
    const full = Array.from({ length: 100 }, (_, i) => convRow(`c${i}`, 'cloud'))
    publishConversationsCache(full)
    await waitFor(() => expect(cell(/Conversations/).textContent).toContain('100+'))
  })

  it('renders an em-dash — never a fabricated 0 — while a count is unknown', () => {
    memories = { memories: [], loading: true }
    renderHub()
    // Conversations has not published yet either: both are unknown, not zero.
    expect(cell(/Memories/).textContent).toContain('—')
    expect(cell(/Memories/).textContent).not.toContain('0')
    expect(cell(/Conversations/).textContent).toContain('—')
  })

  it('renders an em-dash — never 0 — when the memories fetch FAILED', () => {
    // useMemories' `finally` marks the cache loaded even when the request threw, so a
    // failed/offline fetch arrives here as an empty list with loading:false. Keying
    // only on `loading` would tell an offline user they have 0 memories.
    memories = { memories: [], loading: false, error: 'network error' }
    renderHub()
    expect(cell(/Memories/).textContent).toContain('—')
    expect(cell(/Memories/).textContent).not.toContain('0')
  })
})
