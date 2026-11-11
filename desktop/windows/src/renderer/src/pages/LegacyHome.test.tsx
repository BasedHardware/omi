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

// Heavy / side-effectful dependencies stubbed so LegacyHome mounts hermetically.
vi.mock('../lib/firebase', () => ({
  auth: { currentUser: null },
  onAuthStateChanged: () => () => {}
}))
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

// (jsdom provides MutationObserver natively — the page's card re-arm watches its
// kept-alive wrapper's `hidden` class with one, driven directly in the tests.)

import { LegacyHome } from './LegacyHome'

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

describe('LegacyHome — streaming reply reveal (bug 3)', () => {
  it('renders the live assistant reply through RevealMarkdown, not a raw full-text jump', () => {
    render(<LegacyHome />)
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

  it('clips the assistant avatar mark to the round badge (no square-corner poke)', () => {
    // Geometry regression: a square mark larger than the badge radius poked its
    // (opaque) corners past the rounded-full circle → four corner bumps. The fix
    // is mechanical — the badge MUST clip (overflow-hidden + rounded-full) so the
    // square asset can never escape the circle, whatever its size or background.
    render(<LegacyHome />)
    act(() => vi.advanceTimersByTime(1150))
    const logo = document.querySelector('img[alt="Omi"]') as HTMLImageElement | null
    expect(logo).not.toBeNull()
    const badge = logo!.parentElement as HTMLElement
    // The clip is the load-bearing guarantee against the corner poke.
    expect(badge.className).toContain('overflow-hidden')
    expect(badge.className).toContain('rounded-full')
    // Badge h-11 (44px); mark rendered larger (h-14) so it reads clearly, its
    // overflow safely clipped by the badge above.
    expect(badge.className).toContain('h-11')
    expect(badge.className).toContain('w-11')
    expect(logo!.className).toContain('h-14')
    expect(logo!.className).toContain('w-14')
    // First-line alignment: the reply text carries the computed top pad (pt-3)
    // that optically centers its first line on the 44px badge. (Was pt-0.5,
    // tuned for the old 28px badge, which left the text riding the badge's top.)
    const text = badge.nextElementSibling as HTMLElement
    expect(text.className).toContain('pt-3')
  })

  it('gives every bubble the iMessage-style pop-in entrance (user + assistant)', () => {
    // A settled two-turn thread: both bubbles carry the one-shot `.bubble-in`
    // entrance keyed by m.id, so appending a message pops it in once on mount.
    chat.sending = false
    chat.history = [
      { id: 'u1', role: 'user', content: 'Hello Omi' },
      { id: 'a1', role: 'assistant', content: 'Hi there' }
    ]
    const { container } = render(<LegacyHome />)
    act(() => vi.advanceTimersByTime(1150))

    const bubbles = Array.from(container.querySelectorAll('.bubble-in'))
    // The user bubble itself and the assistant turn's wrapper both animate in.
    expect(bubbles.some((el) => el.textContent?.includes('Hello Omi'))).toBe(true)
    expect(bubbles.some((el) => el.textContent?.includes('Hi there'))).toBe(true)
  })
})

describe('LegacyHome — top cards persist per visit, dismiss on click below them', () => {
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
    render(<LegacyHome />)
    advanceToReady()
    // New spec: a visit always starts with the cards up, thread or not.
    expect(isOpen()).toBe(true)
  })

  it('keeps the cards when the cards themselves are clicked (only areas below dismiss)', () => {
    chat.sending = false
    chat.history = []
    render(<LegacyHome />)
    advanceToReady()
    act(() => fireEvent.mouseDown(row()!))
    expect(isOpen()).toBe(true)
  })

  it('dismisses the cards (height 0 + faded) when the chat area below them is clicked', () => {
    chat.sending = false
    chat.history = []
    render(<LegacyHome />)
    advanceToReady()
    expect(isOpen()).toBe(true)
    const below = document.querySelector('[data-testid="chat-below-region"]') as HTMLElement
    act(() => fireEvent.mouseDown(below))
    expect(isCollapsed()).toBe(true)
  })

  it('re-arms the cards when the kept-alive panel becomes visible again (revisit)', async () => {
    chat.sending = false
    chat.history = []
    const { container } = render(<LegacyHome />)
    advanceToReady()
    const below = document.querySelector('[data-testid="chat-below-region"]') as HTMLElement
    act(() => fireEvent.mouseDown(below))
    expect(isCollapsed()).toBe(true)
    // Home's root parent is the panel wrapper MainViews toggles `hidden` on;
    // here the testing-library container plays that wrapper. Leaving Home adds
    // `hidden`; returning removes it — only the return re-arms the cards. The
    // MutationObserver delivers on a microtask, so flush one after each toggle.
    await act(async () => {
      container.classList.add('hidden')
      await Promise.resolve()
    })
    expect(isCollapsed()).toBe(true) // leaving must NOT re-arm
    await act(async () => {
      container.classList.remove('hidden')
      await Promise.resolve()
    })
    expect(isOpen()).toBe(true) // the revisit re-arms
  })
})
