// @vitest-environment jsdom
// Integration coverage for the Hub's intelligence wiring: the knows slot
// replacing the wordmark, question-row prefill pulling ask-bar focus, the
// chat-panel empty-state hosting the rolling knows, and the personalized
// suggestions feed. The slot components are stubbed — their own behavior is
// covered in components/home/knows and lib/intelligence; these tests pin the
// HUB's side of each seam.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HomeHub } from './HomeHub'
import { registerHubKnows, reportHubKnowsPresence, type HubKnowsProps } from './hubKnowsSlot'
import { registerHubHomeWidgets } from './hubHomeWidgetsSlot'

const chat = {
  history: [] as unknown[],
  sending: false,
  send: vi.fn(),
  messages: [] as unknown[]
}
vi.mock('../../../state/appState', () => ({ useAppState: () => ({ chat }) }))
vi.mock('../../../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../../../lib/apiClient', () => ({
  omiApi: { get: vi.fn(async () => ({ data: [] })), post: vi.fn(), delete: vi.fn() },
  desktopApi: { post: vi.fn() }
}))
vi.mock('../../../lib/agentLLM', () => ({ callAgentLLM: vi.fn(async () => '{"questions": []}') }))
vi.mock('../../../lib/actionItems', () => ({ fetchAllActionItems: vi.fn(async () => []) }))
vi.mock('./useHubStats', () => ({
  useHubStats: () => ({ conversations: 0, memories: 0, tasks: 0 })
}))
vi.mock('./HubStatRibbon', () => ({ HubStatRibbon: () => <div data-testid="ribbon" /> }))
vi.mock('./hubConnectSlot', () => ({
  preloadHubConnectContent: vi.fn(),
  getHubConnectContent: () => null
}))
vi.mock('./HubConnectPanel', () => ({ HubConnectPanel: () => <div /> }))
vi.mock('../../chat/HubChatHeader', () => ({ HubChatHeader: () => <div /> }))
vi.mock('../../chat/ChatAppPicker', () => ({ ChatAppPicker: () => <div /> }))
vi.mock('../../chat/ChatMessages', () => ({ ChatMessages: () => <div /> }))
vi.mock('../HomeCanvasBackground', () => ({ HomeCanvasBackground: () => <div /> }))

/* eslint-disable @typescript-eslint/no-empty-function -- no-op stub */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub
;(window as unknown as { omi: Record<string, unknown> }).omi = {
  insightRecent: vi.fn(async () => []),
  rewindGetSettings: vi.fn(async () => ({})),
  onRewindSettings: vi.fn(() => () => {})
}

// The stub renders its props into the DOM instead of writing to an outer
// variable (reassigning during render trips the react-hooks purity lint); the
// prefill test drives the seam through a real click.

function StubKnows(props: HubKnowsProps): React.JSX.Element {
  return (
    <button
      type="button"
      data-testid={`stub-knows-${props.variant ?? 'stage'}`}
      onClick={() => props.onAskPrefill?.('What changed this week?')}
    />
  )
}

beforeEach(() => {
  window.localStorage.clear()
  chat.sending = false
  chat.history = []
  registerHubKnows(StubKnows)
  registerHubHomeWidgets(() => <div data-testid="stub-widgets" />)
  reportHubKnowsPresence(false)
})

afterEach(() => {
  cleanup()
  reportHubKnowsPresence(false)
  vi.restoreAllMocks()
})

describe('the knows slot and the wordmark', () => {
  it('renders the wordmark while the knows list is empty, and swaps when rows appear', async () => {
    render(
      <MemoryRouter>
        <HomeHub />
      </MemoryRouter>
    )
    expect(screen.getByText('omi.')).toBeTruthy()
    reportHubKnowsPresence(true)
    await waitFor(() => expect(screen.queryByText('omi.')).toBeNull())
    expect(screen.getByTestId('stub-knows-stage')).toBeTruthy()
    reportHubKnowsPresence(false)
    await waitFor(() => expect(screen.getByText('omi.')).toBeTruthy())
  })

  it('keeps the knows list mounted while hidden so presence flips cannot loop', () => {
    render(
      <MemoryRouter>
        <HomeHub />
      </MemoryRouter>
    )
    // Present even when the wordmark shows: mounted but visually hidden.
    expect(screen.getByTestId('stub-knows-stage')).toBeTruthy()
  })
})

describe('question prefill', () => {
  it('prefills the ask bar draft and pulls focus via the focus signal', async () => {
    render(
      <MemoryRouter>
        <HomeHub />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('stub-knows-stage'))
    // The focus signal focuses the stage input, whose focus opens the panel and
    // re-docks (remounts) the bar — so assert against the CURRENT input node.
    await waitFor(() => {
      const input = screen.getByDisplayValue('What changed this week?')
      expect(document.activeElement).toBe(input)
    })
  })
})

describe('the chat-mode rolling knows', () => {
  it('mounts the rolling variant inside the empty chat panel', async () => {
    render(
      <MemoryRouter>
        <HomeHub />
      </MemoryRouter>
    )
    // Focusing the ask bar opens the chat panel (the hub's stage machine).
    fireEvent.focus(screen.getByRole('textbox'))
    await waitFor(() => expect(screen.getByTestId('stub-knows-rolling')).toBeTruthy())
  })
})
