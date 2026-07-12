// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, act, fireEvent } from '@testing-library/react'

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

// jsdom has no IntersectionObserver either (Home uses one to re-arm the cards
// when the kept-alive panel becomes visible again). The stub captures the latest
// callback so a test can simulate a "revisit" by firing an intersecting entry.
type IOEntry = { isIntersecting: boolean }
let lastIntersectionCallback: ((entries: IOEntry[]) => void) | null = null
class IntersectionObserverStub {
  constructor(cb: (entries: IOEntry[]) => void) {
    lastIntersectionCallback = cb
  }
  /* eslint-disable @typescript-eslint/no-empty-function -- no-op stub */
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  /* eslint-enable @typescript-eslint/no-empty-function */
}
;(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub

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

  it('renders the assistant avatar logo at the enlarged size (was too small in chat)', () => {
    // The omi mark sits in a white badge next to each assistant turn. It read too
    // small across two rounds (h-7/h-4, then h-10/h-7 at ~70% fill); it is now a
    // h-11 badge with a h-9 mark (~82% fill) so the mark's circles read clearly.
    render(<Home />)
    act(() => vi.advanceTimersByTime(1150))
    const logo = document.querySelector('img[alt="Omi"]') as HTMLImageElement | null
    expect(logo).not.toBeNull()
    expect(logo!.className).toContain('h-9')
    expect(logo!.className).toContain('w-9')
    const badge = logo!.parentElement as HTMLElement
    expect(badge.className).toContain('h-11')
    expect(badge.className).toContain('w-11')
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

describe('Home — top cards persist per visit, dismiss on click below them', () => {
  const row = (): HTMLElement | null => document.querySelector('[data-testid="widgets-row"]')
  const isOpen = (): boolean => {
    const el = row()
    if (!el) return false
    const inner = el.firstElementChild as HTMLElement
    return parseInt(el.style.height, 10) > 0 && inner.className.includes('opacity-100')
  }
  const isCollapsed = (): boolean => {
    const el = row()
    if (!el) return false
    const inner = el.firstElementChild as HTMLElement
    return parseInt(el.style.height, 10) === 0 && inner.className.includes('opacity-0')
  }
  // Widgets reveal once ready — the 6s safety-net timer flips readiness here,
  // since the mocked widgets never fire onReady.
  const advanceToReady = (): void => {
    act(() => vi.advanceTimersByTime(6000))
  }

  it('shows the cards on mount even when a conversation already exists', () => {
    chat.sending = false
    chat.history = [{ id: 'u1', role: 'user', content: 'Hello Omi' }]
    render(<Home />)
    advanceToReady()
    // New spec: a visit always starts with the cards up, thread or not.
    expect(isOpen()).toBe(true)
  })

  it('keeps the cards when the cards themselves are clicked (only areas below dismiss)', () => {
    chat.sending = false
    chat.history = []
    render(<Home />)
    advanceToReady()
    act(() => fireEvent.mouseDown(row()!))
    expect(isOpen()).toBe(true)
  })

  it('dismisses the cards (height 0 + faded) when the chat area below them is clicked', () => {
    chat.sending = false
    chat.history = []
    render(<Home />)
    advanceToReady()
    expect(isOpen()).toBe(true)
    const below = document.querySelector('[data-testid="chat-below-region"]') as HTMLElement
    act(() => fireEvent.mouseDown(below))
    expect(isCollapsed()).toBe(true)
  })

  it('re-arms the cards when the kept-alive panel becomes visible again (revisit)', () => {
    chat.sending = false
    chat.history = []
    render(<Home />)
    advanceToReady()
    const below = document.querySelector('[data-testid="chat-below-region"]') as HTMLElement
    act(() => fireEvent.mouseDown(below))
    expect(isCollapsed()).toBe(true)
    // Simulate navigating away and back: MainViews keeps Home mounted, so the
    // IntersectionObserver firing "intersecting" is what a revisit looks like.
    act(() => lastIntersectionCallback?.([{ isIntersecting: true }]))
    expect(isOpen()).toBe(true)
  })
})
