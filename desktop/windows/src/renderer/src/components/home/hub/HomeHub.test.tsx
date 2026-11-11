// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// The Hub drives the app's ONE chat engine — asserted here by checking that a submit
// calls the shared chat.send, not some second message array of its own.

type ChatMsg = { id?: string; role: 'user' | 'assistant'; content: string }
let chat: {
  history: ChatMsg[]
  sending: boolean
  send: ReturnType<typeof vi.fn>
  // The multi-chat header's slice of the engine (used only by the popover suite).
  selectedAppId?: string | null
  currentThreadId?: string | null
  switchThread?: ReturnType<typeof vi.fn>
}
vi.mock('../../../state/appState', () => ({ useAppState: () => ({ chat }) }))

// The multi-chat header's session list. Stubbed so the popover suite exercises the
// real header + real Radix popover without a live sessions backend.
let sessions: Record<string, unknown>
vi.mock('../../../hooks/useChatSessions', () => ({ useChatSessions: () => sessions }))

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
import { setPreferences } from '../../../lib/preferences'

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
  sessions = {}
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
    // useHubStats subscribes to the task store so the Tasks count stays live.
    onTasksChanged: vi.fn().mockReturnValue(() => {}),
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

  it('returns to the hub from the chat panel own close control', () => {
    // Esc and a click on the paper both leave the panel, but neither is VISIBLE:
    // users reached the chat panel and could not tell how to get back (#10894).
    renderHub()
    expect(screen.queryByLabelText('Close chat')).toBeNull()

    fireEvent.focus(askBar())
    expect(mode()).toBe('chat')

    // A real press is mousedown → click; the click-outside listener rides mousedown.
    const close = screen.getByLabelText('Close chat')
    fireEvent.mouseDown(close)
    fireEvent.click(close)

    expect(mode()).toBe('hub')
    expect(screen.getByText('omi.')).not.toBeNull()
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

  it('renders a LIVE paperclip — attachments now have a real backing path', () => {
    // Once the paperclip was omitted precisely because clicking would do nothing.
    // Track 1 shipped the attachment API (window.omi.openChatFiles + the pending
    // list), so the paperclip is now a real control that opens the picker — its
    // detailed behavior is covered in HubAskBar.test.tsx.
    renderHub()
    expect(screen.getByLabelText('Attach files')).not.toBeNull()
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

describe('HomeHub — portaled panel UI does not read as a click-outside', () => {
  // #10895 / #10896: with the multi-chat header on, clicking "+" or rename inside
  // the chat-history popover dropped the user back on the resting hub and the
  // button never fired. The popover is PORTALED to <body>, so the panel's
  // click-outside check ("not inside the stage") counted a mousedown on it as a
  // dismiss — which unmounted the popover before the click landed.
  const SESSION = {
    id: 's1',
    title: 'Trip planning',
    preview: 'where should we go',
    createdAt: 0,
    updatedAt: Date.now(),
    messageCount: 2,
    starred: false
  }

  let createNewSession: ReturnType<typeof vi.fn>
  let renameSession: ReturnType<typeof vi.fn>

  beforeEach(() => {
    // Radix Popover needs a couple of DOM APIs jsdom lacks; stub them so open works.
    if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
    if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

    setPreferences({ multiChatEnabled: true })
    ;(window as unknown as { omi: Record<string, unknown> }).omi.chatGetEngine = vi
      .fn()
      .mockResolvedValue('pi_mono')

    chat.selectedAppId = null
    chat.currentThreadId = null
    chat.switchThread = vi.fn()

    createNewSession = vi.fn().mockResolvedValue({ ...SESSION, id: 's2' })
    renameSession = vi.fn().mockResolvedValue(undefined)
    sessions = {
      sessions: [SESSION],
      filteredSessions: [SESSION],
      groupedSessions: [{ label: 'Today', sessions: [SESSION] }],
      currentSessionId: null,
      loading: false,
      error: null,
      createError: null,
      searchQuery: '',
      showStarredOnly: false,
      setSearchQuery: vi.fn(),
      toggleStarredFilter: vi.fn(),
      retryLoad: vi.fn(),
      clearCreateError: vi.fn(),
      selectSession: vi.fn(),
      createNewSession,
      renameSession,
      toggleStar: vi.fn().mockResolvedValue(undefined),
      removeSession: vi.fn().mockResolvedValue(undefined)
    }
  })
  afterEach(() => setPreferences({ multiChatEnabled: false }))

  /** Open the chat panel, then the chat-history popover, and return its panel. */
  const openHistory = async (): Promise<HTMLElement> => {
    renderHub()
    fireEvent.focus(askBar())
    expect(mode()).toBe('chat')
    const trigger = await screen.findByTitle('Chat history')
    fireEvent.click(trigger)
    return await screen.findByRole('dialog')
  }

  it('keeps the chat panel open when "+" in the chat-history popover is pressed', async () => {
    const popover = await openHistory()
    const plus = within(popover).getByTitle('New chat')

    // A real press is mousedown → click; the dismiss listener rides mousedown.
    fireEvent.mouseDown(plus)
    fireEvent.click(plus)

    expect(mode()).toBe('chat')
    expect(createNewSession).toHaveBeenCalled()
    await waitFor(() => expect(chat.switchThread).toHaveBeenCalledWith('s2'))
  })

  it('keeps the chat panel open while renaming a chat from the popover', async () => {
    const popover = await openHistory()
    const rename = within(popover).getByTitle('Rename')

    fireEvent.mouseDown(rename)
    fireEvent.click(rename)
    expect(mode()).toBe('chat')

    const input = within(await screen.findByRole('dialog')).getByDisplayValue('Trip planning')
    fireEvent.change(input, { target: { value: 'Iceland trip' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(mode()).toBe('chat')
    expect(renameSession).toHaveBeenCalledWith('s1', 'Iceland trip')
  })

  it('lays the close control out in the SAME row as the multi-chat controls', async () => {
    // jsdom has no layout, so the only honest guard against the close control
    // landing on top of "+" / history is structural: one flex row owns all three.
    renderHub()
    fireEvent.focus(askBar())
    const history = await screen.findByTitle('Chat history')
    const row = screen.getByLabelText('Close chat').parentElement as HTMLElement

    expect(row.className).toContain('flex')
    expect(row.contains(history)).toBe(true)
  })

  it('still dismisses the panel on a mousedown on the Hub paper outside the stage', () => {
    // The guard above must not disable click-outside itself: the Hub's own paper
    // (here, the floating header band) still returns the stage to the resting hub.
    renderHub()
    fireEvent.focus(askBar())
    expect(mode()).toBe('chat')

    fireEvent.mouseDown(screen.getByText('Capture'))
    expect(mode()).toBe('hub')
  })
})
