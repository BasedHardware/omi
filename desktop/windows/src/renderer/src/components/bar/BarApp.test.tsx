// @vitest-environment jsdom
// Regression tests for the bar's reveal/expand view reset. The bug: the peek
// pill's click-to-expand (bar:mode 'expanded') re-rendered whatever view the
// renderer was last in — a stale conversation/agent surface — instead of the hub
// with the "Ask Omi anything" composer. A collapse (bar:mode 'peek') keeps this
// renderer mounted and does NOT reset view, so a collapse→expand cycle exposed
// it. Mac spec: the thing labeled "Ask Omi anything" ALWAYS lands at the input.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, act } from '@testing-library/react'
import type { AgentPill } from './agentPills'

// --- heavy / native-ish dependencies stubbed to inert shapes ------------------
vi.mock('../orb/Orb', () => ({ Orb: () => <div data-testid="orb" /> }))
vi.mock('../../hooks/usePushToTalk', () => ({
  usePushToTalk: () => ({
    recording: false,
    locked: false,
    transcribing: false,
    hint: null,
    error: null,
    analyserRef: { current: null },
    onKeyDown: () => false,
    onKeyUp: () => false,
    beginHold: vi.fn(),
    endHold: vi.fn(),
    cancel: vi.fn()
  })
}))
vi.mock('../../hooks/useVoicePlaneSupervisor', () => ({
  useVoicePlaneSupervisor: () => ({ chip: null, noteCancel: vi.fn() })
}))
vi.mock('../../lib/firebase', () => ({
  auth: { authStateReady: async () => {} }
}))
vi.mock('../../lib/preferences', () => ({
  getPreferences: () => ({}),
  onPreferencesChange: () => () => {}
}))
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { uid: 'u1' }, loading: false })
}))
vi.mock('./barSend', () => ({
  createBarSender: () => ({
    send: vi.fn(async () => null),
    sync: vi.fn(async () => {}),
    checkSync: vi.fn(() => null)
  })
}))
// The message list is markdown-heavy and tested elsewhere.
vi.mock('../chat/ChatMessages', () => ({
  ChatMessages: ({ messages }: { messages: unknown[] }) => (
    <div data-testid="messages">{messages.length}</div>
  )
}))

// useAgentPills is controllable per test (for the agent-view path).
let mockPills: AgentPill[] = []
vi.mock('../../hooks/useAgentPills', () => ({
  useAgentPills: () => ({
    pills: mockPills,
    markViewed: vi.fn(),
    dismiss: vi.fn(),
    transcriptFor: () => ({ messages: [], sending: false })
  })
}))

/* eslint-disable @typescript-eslint/no-empty-function -- jsdom stubs */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

// Capture the IPC callbacks BarApp registers so tests can fire main→renderer events.
type Cb = (...a: unknown[]) => void
const ipc: Record<string, Cb> = {}
function capture(name: string) {
  return (cb: Cb) => {
    ipc[name] = cb
    return () => {}
  }
}

beforeEach(() => {
  mockPills = []
  for (const k of Object.keys(ipc)) delete ipc[k]
  ;(globalThis as unknown as { requestAnimationFrame: unknown }).requestAnimationFrame = (
    cb: FrameRequestCallback
  ) => {
    cb(0)
    return 0
  }
  ;(window as unknown as { omiBar: unknown }).omiBar = {
    onShow: capture('onShow'),
    onMode: capture('onMode'),
    onWillHide: capture('onWillHide'),
    onChatState: capture('onChatState'),
    onPtt: capture('onPtt'),
    onVoiceHubState: capture('onVoiceHubState'),
    onVoicePlaybackLevel: capture('onVoicePlaybackLevel'),
    requestChatState: vi.fn(),
    ready: vi.fn(),
    showAck: vi.fn(),
    expand: vi.fn(),
    keepAlive: vi.fn(),
    setInteractive: vi.fn(),
    notifyUsageLimit: vi.fn(),
    interruptTts: vi.fn(),
    voiceHubBegin: vi.fn(),
    voiceHubEnd: vi.fn(),
    voiceHubCancel: vi.fn()
  }
  ;(window as unknown as { omiOverlay: unknown }).omiOverlay = {
    focusMain: vi.fn(),
    hide: vi.fn(),
    notifyVoiceCaptured: vi.fn(),
    notifyVoiceFailed: vi.fn()
  }
  ;(window as unknown as { omi: unknown }).omi = { e2e: false, agentControlCall: vi.fn() }
})

afterEach(() => cleanup())

async function mountBar() {
  const mod = await import('./BarApp')
  let utils!: ReturnType<typeof render>
  await act(async () => {
    utils = render(<mod.BarApp />)
    // flush auth.authStateReady() → authReady=true so real content renders.
    await Promise.resolve()
    await Promise.resolve()
  })
  return utils
}

const fire = (name: string, ...args: unknown[]) =>
  act(() => {
    ipc[name]?.(...args)
  })

/** The hub (list) view is identified by its "Ask Omi anything…" composer. */
const hubInput = () =>
  document.querySelector('textarea[placeholder^="Ask Omi anything"]') as HTMLTextAreaElement | null
/** The conversation view's composer placeholder differs ("Ask Omi…  ·  hold…"). */
const conversationInput = () =>
  document.querySelector('textarea[placeholder^="Ask Omi…"]') as HTMLTextAreaElement | null

async function enterConversation() {
  const ta = hubInput()
  expect(ta).toBeTruthy()
  fireEvent.change(ta!, { target: { value: 'hello' } })
  await act(async () => {
    fireEvent.keyDown(ta!, { key: 'Enter' })
    await Promise.resolve()
  })
  expect(conversationInput()).toBeTruthy()
}

describe('BarApp reveal/expand view reset (peek-landing bug)', () => {
  it('collapse→expand lands on the hub composer, not the stale conversation', async () => {
    await mountBar()
    // Reveal expanded → hub.
    await fire('onShow', { mode: 'expanded', token: 1 })
    expect(hubInput()).toBeTruthy()

    // Send → conversation view.
    await enterConversation()

    // Collapse to a peek pill (bar:mode 'peek') — renderer stays mounted, view
    // is intentionally not reset here (the pill shows no view content).
    await fire('onMode', 'peek')

    // Click-to-expand (bar:mode 'expanded'): MUST reset to the hub composer.
    await fire('onMode', 'expanded')
    expect(hubInput()).toBeTruthy()
    expect(conversationInput()).toBeNull()
    // Focus-on-appear: the cursor lands in the hub input (Mac focusOnAppear).
    expect(document.activeElement).toBe(hubInput())
  })

  it('collapse→expand lands on the hub composer from the AGENT transcript too', async () => {
    mockPills = [
      {
        id: 'p1',
        runId: 'r1',
        sessionId: 's1',
        title: 'My Agent Run',
        displayStatus: 'running',
        latestActivity: 'working…',
        query: 'do a thing',
        createdAtMs: 1,
        completedAtMs: null,
        errorMessage: null,
        provider: null,
        viewedAtMs: null
      }
    ]
    await mountBar()
    await fire('onShow', { mode: 'expanded', token: 1 })

    // Open the pill's own transcript → agent view (no hub/conversation input).
    await act(async () => {
      fireEvent.click(screen.getByText('My Agent Run'))
      await Promise.resolve()
    })
    expect(hubInput()).toBeNull()
    expect(conversationInput()).toBeNull()

    // Collapse then re-expand → back to the hub composer, pill transcript closed.
    await fire('onMode', 'peek')
    await fire('onMode', 'expanded')
    expect(hubInput()).toBeTruthy()
    expect(document.activeElement).toBe(hubInput())
  })

  it('a fresh reveal (onShow) also resets a stale conversation view to the hub', async () => {
    await mountBar()
    await fire('onShow', { mode: 'expanded', token: 1 })
    await enterConversation()

    // Hide, then reveal again as a pill: onShow resets to the hub.
    await fire('onWillHide')
    await fire('onShow', { mode: 'peek', token: 2 })
    // Not expanded yet (pill) — but the view underneath is already the hub.
    await fire('onMode', 'expanded')
    expect(hubInput()).toBeTruthy()
    expect(conversationInput()).toBeNull()
  })
})
