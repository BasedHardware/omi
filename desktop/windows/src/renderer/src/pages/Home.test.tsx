// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'

// Bug 3 regression: the main window streamed the assistant reply as raw
// <Markdown text={m.content} />, so every SSE chunk landed as a bulky jump. It
// now renders the live reply through RevealMarkdown (a char-by-char reveal), so
// the text grows smoothly instead of in chunks. This asserts the wiring: the
// streaming last message shows a growing PREFIX, never the full string at once.

// Read the on-screen text verbatim by stubbing the markdown renderer.
vi.mock('../components/Markdown', () => ({
  Markdown: ({ text }: { text: string }) => <span data-testid="md">{text}</span>
}))

// Heavy / side-effectful dependencies stubbed so Home mounts hermetically.
vi.mock('../lib/firebase', () => ({
  auth: { currentUser: null },
  onAuthStateChanged: () => () => {}
}))
vi.mock('../lib/kgSynthesis', () => ({ maybeBuildLocalGraph: vi.fn() }))
vi.mock('../lib/screenSynthesis', () => ({ maybeStartScreenSynthesis: vi.fn() }))
vi.mock('../lib/insightEngine', () => ({ maybeStartInsightEngine: vi.fn() }))
vi.mock('../lib/retentionSweep', () => ({ maybeStartRetentionSweep: vi.fn() }))
vi.mock('../components/home/QuickTaskWidget', () => ({ QuickTaskWidget: () => null }))
vi.mock('../components/home/QuickGoalsWidget', () => ({ QuickGoalsWidget: () => null }))
vi.mock('../components/voice/VoiceSessionSurface', () => ({ VoiceSessionSurface: () => null }))

type ChatMsg = { id?: string; role: 'user' | 'assistant'; content: string }
let chat: {
  history: ChatMsg[]
  sending: boolean
  speaking: boolean
  agentActive: boolean
  send: () => void
  reset: () => void
}
vi.mock('../state/appState', () => ({ useAppState: () => ({ chat }) }))

// jsdom has no ResizeObserver (the widget-measure and content-follow effects use it).
/* eslint-disable @typescript-eslint/no-empty-function -- no-op stub */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

import { Home } from './Home'

const LONG = 'The quick brown fox jumps over the lazy dog and keeps on running along the road.'

beforeEach(() => {
  vi.useFakeTimers()
  chat = {
    history: [{ id: 'a1', role: 'assistant', content: LONG }],
    sending: true,
    speaking: false,
    agentActive: false,
    send: vi.fn(),
    reset: vi.fn()
  }
})
afterEach(() => {
  vi.useRealTimers()
  cleanup()
})

const md = (): HTMLElement | null => document.querySelector('[data-testid="md"]')

describe('Home — streaming reply reveal (bug 3)', () => {
  it('renders the live assistant reply through RevealMarkdown, not a raw full-text jump', () => {
    render(<Home />)
    // Bar slides down and the thread reveals after its lead-in (150 + 1000ms).
    act(() => vi.advanceTimersByTime(1150))

    // The full reply is already in state, but only a prefix is on screen — a raw
    // <Markdown> would show the whole string at once. This is the bug-3 guard.
    expect(md()).not.toBeNull()
    expect(md()!.textContent!.length).toBeLessThan(LONG.length)

    // The reveal ticks the prefix up to the full reply and stops there.
    act(() => vi.advanceTimersByTime(3000))
    expect(md()!.textContent).toBe(LONG)
  })

  it('gives every bubble the iMessage-style pop-in entrance (user + assistant)', () => {
    // A settled two-turn thread: both bubbles carry the one-shot `.bubble-in`
    // entrance keyed by m.id, so appending a message pops it in once on mount.
    chat.sending = false
    chat.history = [
      { id: 'u1', role: 'user', content: 'Hello Omi' },
      { id: 'a1', role: 'assistant', content: 'Hi there' }
    ]
    const { container } = render(<Home />)
    act(() => vi.advanceTimersByTime(1150))

    const bubbles = Array.from(container.querySelectorAll('.bubble-in'))
    // The user bubble itself and the assistant turn's wrapper both animate in.
    expect(bubbles.some((el) => el.textContent?.includes('Hello Omi'))).toBe(true)
    expect(bubbles.some((el) => el.textContent?.includes('Hi there'))).toBe(true)
  })
})
