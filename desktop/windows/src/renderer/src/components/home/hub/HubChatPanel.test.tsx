// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, fireEvent, act } from '@testing-library/react'
import { HubChatPanel } from './HubChatPanel'
import type { ChatMsg } from '../../../hooks/useChat'

// The panel pins the live edge with a ResizeObserver (absent in jsdom). Capture
// the callback so the test can fire it to simulate the streaming reply growing.
let roCallback: (() => void) | null = null
/* eslint-disable @typescript-eslint/no-empty-function -- no-op ResizeObserver stub */
class ResizeObserverStub {
  constructor(cb: () => void) {
    roCallback = cb
  }
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

// Markdown rendering is tested elsewhere; stub the list so this test focuses on
// the scroll-follow behavior.
vi.mock('../../chat/ChatMessages', () => ({
  ChatMessages: ({ messages }: { messages: unknown[] }) => (
    <div data-testid="messages">{messages.length}</div>
  )
}))

const messages: ChatMsg[] = [
  { id: 'u1', role: 'user', content: 'hello' },
  { id: 'a1', role: 'assistant', content: 'streaming answer...' }
]

function renderPanel(): HTMLDivElement {
  const { container } = render(
    <HubChatPanel messages={messages} sending={true} onDismiss={() => {}}>
      <div>ask bar</div>
    </HubChatPanel>
  )
  const el = container.querySelector('.overflow-y-auto') as HTMLDivElement
  // jsdom has no layout, so fake the scroll geometry: a 1000px document in a
  // 300px viewport.
  Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: 300, configurable: true })
  return el
}

afterEach(() => {
  cleanup()
  roCallback = null
})

describe('HubChatPanel live-edge follow', () => {
  it('pins to the bottom while following as the reply grows', () => {
    const el = renderPanel()
    el.scrollTop = 0
    act(() => roCallback?.())
    expect(el.scrollTop).toBe(1000)
  })

  it('does NOT yank the reader back to the bottom after they scroll up mid-stream', () => {
    const el = renderPanel()
    // Reader scrolls up to read earlier messages during generation.
    fireEvent.wheel(el, { deltaY: -40 })
    el.scrollTop = 200
    // Streaming appends more text -> ResizeObserver fires again.
    act(() => roCallback?.())
    // The view must stay where the reader left it, not jump to the live edge.
    expect(el.scrollTop).toBe(200)
  })

  // #10505: the reader dragged the scrollbar thumb / hit PageUp instead of using
  // the wheel, and the next streamed chunk yanked them straight back down — the
  // wheel-only release never fired, so the panel thought it was still following.
  it('does NOT yank the reader back after a scroll up with no wheel (scrollbar drag, PageUp)', () => {
    const el = renderPanel()
    act(() => roCallback?.()) // following the stream at the live edge
    // The reader drags up; the browser reports it as a plain scroll event.
    el.scrollTop = 200
    fireEvent.scroll(el)
    act(() => roCallback?.())
    expect(el.scrollTop).toBe(200)
  })

  it('keeps following when a shrinking thread clamps the viewport to the bottom', () => {
    const el = renderPanel()
    // Start pinned at the live edge, then the thread shrinks (switched/cleared
    // chat): the browser clamps scrollTop DOWN, which must not read as the reader
    // scrolling away — the viewport is still at the bottom.
    act(() => roCallback?.())
    Object.defineProperty(el, 'scrollHeight', { value: 400, configurable: true })
    el.scrollTop = 100 // 400 - 100 - 300 = 0 -> still at the edge
    fireEvent.scroll(el)
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true })
    act(() => roCallback?.())
    expect(el.scrollTop).toBe(1000)
  })

  it('re-engages following once the reader returns to the live edge', () => {
    const el = renderPanel()
    fireEvent.wheel(el, { deltaY: -40 })
    el.scrollTop = 200
    act(() => roCallback?.())
    expect(el.scrollTop).toBe(200)
    // Reader scrolls back down to within the bottom threshold.
    el.scrollTop = 700 // 1000 - 700 - 300 = 0 <= 8 -> at bottom
    fireEvent.scroll(el)
    el.scrollTop = 400
    act(() => roCallback?.())
    expect(el.scrollTop).toBe(1000)
  })
})
