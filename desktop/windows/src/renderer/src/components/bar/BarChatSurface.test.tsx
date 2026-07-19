// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { useState } from 'react'
import { render, cleanup, fireEvent, screen, act } from '@testing-library/react'
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

function makeProps(overrides: Partial<BarChatSurfaceProps> = {}): BarChatSurfaceProps {
  return {
    chat: baseChat,
    view: 'list',
    expanded: true,
    conversationTitle: 'Omi Chat',
    onOpenConversation: vi.fn(),
    pills: [],
    onOpenPill: vi.fn(),
    onDismissPill: vi.fn(),
    onBack: vi.fn(),
    onClose: vi.fn(),
    draft: '',
    setDraft: vi.fn(),
    onSubmit: vi.fn(async () => null),
    pttKeyDown: vi.fn(() => false),
    pttKeyUp: vi.fn(() => false),
    recording: false,
    transcribing: false,
    maxListHeight: 300,
    ...overrides
  }
}

function renderSurface(overrides: Partial<BarChatSurfaceProps> = {}): BarChatSurfaceProps {
  const props = makeProps(overrides)
  render(<BarChatSurface {...props} />)
  return props
}

/** The surface wired to REAL draft state (renderSurface's setDraft is a spy, so the
 *  input never actually changes there). A submit's clear, the user's next keystrokes
 *  and a late restore all land in the same live input — the only way to exercise the
 *  ordering between two in-flight sends. */
function renderLiveSurface(
  onSubmit: (text: string) => Promise<string | null>
): HTMLTextAreaElement {
  function Harness(): React.JSX.Element {
    const [draft, setDraft] = useState('')
    return (
      <BarChatSurface
        chat={baseChat}
        view="conversation"
        expanded={true}
        conversationTitle="Omi Chat"
        onOpenConversation={vi.fn()}
        pills={[]}
        onOpenPill={vi.fn()}
        onDismissPill={vi.fn()}
        onBack={vi.fn()}
        onClose={vi.fn()}
        draft={draft}
        setDraft={setDraft}
        onSubmit={onSubmit}
        pttKeyDown={vi.fn(() => false)}
        pttKeyUp={vi.fn(() => false)}
        recording={false}
        transcribing={false}
        maxListHeight={300}
      />
    )
  }
  render(<Harness />)
  return screen.getByPlaceholderText(/Ask Omi/i) as HTMLTextAreaElement
}

afterEach(() => cleanup())

describe('BarChatSurface', () => {
  it('list: the hub hosts the Ask-Omi input, and clicking/focusing it does NOT navigate', () => {
    // Regression for the reported bug: the hub used to be an "Omi Chat" row whose
    // single click opened the conversation. Mac (AskAIInputView / .mainInput) puts
    // an inline focused input here instead — clicking/focusing just seats the
    // cursor; nothing navigates until the user sends.
    const props = renderSurface({ view: 'list' })
    const input = screen.getByPlaceholderText(/Ask Omi/i)
    expect(input).toBeTruthy()
    fireEvent.click(input)
    fireEvent.focus(input)
    expect(props.onOpenConversation).not.toHaveBeenCalled()
  })

  it('list: Enter in the hub input sends ONCE and opens the conversation with the typed text', () => {
    // The send is the only transition to the response state (.mainInput → .mainResponse):
    // onSubmit fires exactly once, the surface flips to the Omi thread (null target),
    // and the shared draft is cleared (INV-CHAT-1 — one thread carries the text).
    const props = renderSurface({ view: 'list', draft: 'what is on my calendar' })
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Enter' })
    expect(props.onSubmit).toHaveBeenCalledTimes(1)
    expect(props.onSubmit).toHaveBeenCalledWith('what is on my calendar')
    expect(props.onOpenConversation).toHaveBeenCalledTimes(1)
    expect(props.setDraft).toHaveBeenCalledWith('')
  })

  it('list: the Send button sends and opens the conversation', () => {
    const props = renderSurface({ view: 'list', draft: 'hello there' })
    fireEvent.click(screen.getByText('Send'))
    expect(props.onSubmit).toHaveBeenCalledWith('hello there')
    expect(props.onOpenConversation).toHaveBeenCalledTimes(1)
  })

  it('list: an empty draft cannot send (Enter is a no-op, Send is disabled)', () => {
    const props = renderSurface({ view: 'list', draft: '' })
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Enter' })
    expect(props.onSubmit).not.toHaveBeenCalled()
    expect(props.onOpenConversation).not.toHaveBeenCalled()
    expect((screen.getByText('Send') as HTMLButtonElement).disabled).toBe(true)
  })

  it('list: Esc with text clears the draft in place and does NOT navigate (Mac: clears inline)', () => {
    const props = renderSurface({ view: 'list', draft: 'draft text' })
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Escape' })
    expect(props.setDraft).toHaveBeenCalledWith('')
    expect(props.onOpenConversation).not.toHaveBeenCalled()
    expect(props.onSubmit).not.toHaveBeenCalled()
  })

  it('list: Esc with an empty draft is left to the window handler (no local clear)', () => {
    // An already-idle hub lets Esc bubble to BarApp's window handler (which hides
    // the bar) — the local handler only intercepts when there is text to clear.
    const props = renderSurface({ view: 'list', draft: '' })
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Escape' })
    expect(props.setDraft).not.toHaveBeenCalled()
  })

  it('list: Esc with a whitespace-only draft still bubbles (a stray space must not eat the close)', () => {
    // draft.trim() gates the local clear, so a blank-but-nonempty draft is treated
    // as idle: Esc bubbles to the window handler that closes the bar.
    const onWindowKeyDown = vi.fn()
    window.addEventListener('keydown', onWindowKeyDown)
    try {
      renderSurface({ view: 'list', draft: '   ' })
      fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Escape' })
      expect(onWindowKeyDown).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener('keydown', onWindowKeyDown)
    }
  })

  it('list: a text-bearing Escape is consumed locally and never reaches the window handler; an empty one bubbles', () => {
    // End-to-end propagation proof (not just the local callback): the hub Esc clears
    // the draft in place AND stops propagating, so BarApp's window-level keydown —
    // which hides the bar — does not also fire. An already-empty hub lets Esc
    // through so a second press still closes the bar.
    const onWindowKeyDown = vi.fn()
    window.addEventListener('keydown', onWindowKeyDown)
    try {
      const withText = makeProps({ view: 'list', draft: 'unsent question' })
      const { unmount } = render(<BarChatSurface {...withText} />)
      fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Escape' })
      expect(withText.setDraft).toHaveBeenCalledWith('')
      expect(onWindowKeyDown).not.toHaveBeenCalled()
      unmount()
      onWindowKeyDown.mockClear()

      const empty = makeProps({ view: 'list', draft: '' })
      render(<BarChatSurface {...empty} />)
      fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Escape' })
      expect(empty.setDraft).not.toHaveBeenCalled()
      expect(onWindowKeyDown).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener('keydown', onWindowKeyDown)
    }
  })

  it('list: the hub input is focused only once the surface EXPANDS, not while collapsed (persistent mount)', () => {
    // Regression for the auto-focus Major: BarChatSurface stays mounted while the
    // bar is a collapsed pill, so a focus effect keyed only on [view] fires once at
    // startup against the hidden textarea and never again when the pill expands (the
    // MODE flips while view stays 'list'). Mount collapsed → the input must NOT grab
    // focus; flip expanded → it focuses (Mac AskAIInputView focusOnAppear).
    const props = makeProps({ view: 'list', expanded: false })
    const { rerender } = render(<BarChatSurface {...props} />)
    const input = screen.getByPlaceholderText(/Ask Omi/i)
    expect(document.activeElement).not.toBe(input)
    rerender(<BarChatSurface {...props} expanded={true} />)
    expect(document.activeElement).toBe(input)
  })

  it('list: the hub with zero pills shows only the composer — no idle connected-agent rows', () => {
    // Mac parity (FloatingControlBarView): the bar's list is STRICTLY
    // pills-for-actual-runs. There is no persistent "Claude Code" summon row —
    // connecting agents lives in Settings → Agents. A hub with no runs is just the
    // Ask-Omi composer.
    renderSurface({ view: 'list', pills: [] })
    expect(screen.getByPlaceholderText(/Ask Omi/i)).toBeTruthy()
    expect(screen.queryByText('Claude Code')).toBeNull()
    expect(screen.queryByText('Ready')).toBeNull()
    // The only button is the Send control (no agent-summon rows).
    const listButtons = screen
      .getAllByRole('button')
      .filter((b) => b.querySelector('span.rounded-full'))
    expect(listButtons.length).toBe(0)
  })

  it('list: the hub with pills shows the run pills (the only agent surface in the bar)', () => {
    const pill = {
      id: 'p1',
      runId: 'r1',
      sessionId: 's1',
      title: 'Refactor the parser',
      displayStatus: 'running' as const,
      latestActivity: 'Editing files…',
      query: 'refactor the parser',
      createdAtMs: 1,
      completedAtMs: null,
      errorMessage: null,
      provider: null,
      viewedAtMs: null
    }
    const props = renderSurface({ view: 'list', pills: [pill] })
    expect(screen.getByText('Refactor the parser')).toBeTruthy()
    expect(screen.getByText('Editing files…')).toBeTruthy()
    // A pill opens its OWN run transcript, never the shared Omi thread.
    fireEvent.click(screen.getByText('Refactor the parser'))
    expect(props.onOpenPill).toHaveBeenCalledWith('p1')
    expect(props.onOpenConversation).not.toHaveBeenCalled()
  })

  it('conversation: header renders the passed title prop (data-driven, not hardcoded)', () => {
    renderSurface({ view: 'conversation', conversationTitle: 'Omi Chat' })
    expect(screen.getByText('Omi Chat')).toBeTruthy()
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

  it('conversation: an IN-QUOTA send clears the input and leaves it cleared (no restore)', async () => {
    const props = renderSurface({ view: 'conversation', draft: 'hello there' })
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Enter' })
    await vi.waitFor(() => expect(props.onSubmit).toHaveBeenCalled())
    // The only draft write is the immediate clear — normal typing is untouched.
    expect(props.setDraft).toHaveBeenCalledTimes(1)
    expect(props.setDraft).toHaveBeenCalledWith('')
  })

  it('conversation: a BLOCKED send RESTORES the draft — the usage limit must not eat the question', async () => {
    // Regression: the input was cleared before the send, and a send refused by the
    // usage limit never reaches the transcript — so the user's typed question just
    // vanished behind the amber notice and had to be retyped.
    const onSubmit = vi.fn(async () => "You've reached your monthly free message limit.")
    const props = renderSurface({ view: 'conversation', draft: 'what is on my calendar', onSubmit })
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Omi/i), { key: 'Enter' })

    await vi.waitFor(() => expect(props.setDraft).toHaveBeenCalledTimes(2))
    expect(props.setDraft).toHaveBeenNthCalledWith(1, '')
    const restore = vi.mocked(props.setDraft).mock.calls[1][0] as (c: string) => string
    expect(restore('')).toBe('what is on my calendar')
    // …but never clobber text the user typed while the check was in flight.
    expect(restore('a new question')).toBe('a new question')
  })

  it('conversation: a SUPERSEDED blocked send never resurrects itself over the newer question', async () => {
    // Nothing disables the textarea while a check is in flight (only the Send
    // BUTTON is), so Enter can fire a second send while the first cold-start quota
    // probe is still awaiting — both then refuse. The restore must belong to the
    // LAST submit: an "current is empty ⇒ restore" test alone would put the stale
    // first question back (it lands into the input the second submit just cleared)
    // and then the second restore, seeing non-empty text, would keep it — losing
    // the question the user actually asked last.
    const blocked = "You've reached your monthly free message limit."
    const resolvers: ((notice: string | null) => void)[] = []
    const onSubmit = vi.fn(() => new Promise<string | null>((resolve) => resolvers.push(resolve)))
    const input = renderLiveSurface(onSubmit)

    fireEvent.change(input, { target: { value: 'first question' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(input.value).toBe('')
    fireEvent.change(input, { target: { value: 'second question' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(input.value).toBe('')
    expect(onSubmit).toHaveBeenNthCalledWith(1, 'first question')
    expect(onSubmit).toHaveBeenNthCalledWith(2, 'second question')

    // Both sends were awaiting the same deduped cold-start sync, so they refuse in
    // submit order.
    await act(async () => {
      resolvers[0](blocked)
      resolvers[1](blocked)
    })

    expect(input.value).toBe('second question')
  })

  it('conversation: a failed PTT hold surfaces its hint/error inline above the input', () => {
    // While the panel is open, holding Space in the textarea can fail (too short,
    // dead mic, mic unavailable, transcription failed). The hook computes the copy;
    // the panel must show it (the collapsed pill shows it below the pill instead).
    renderSurface({ view: 'conversation', pttNotice: 'Hold longer to record' })
    expect(screen.getByText('Hold longer to record')).toBeTruthy()
    cleanup()
    renderSurface({ view: 'conversation', pttNotice: 'Microphone unavailable' })
    expect(screen.getByText('Microphone unavailable')).toBeTruthy()
  })

  it('conversation: no PTT notice → no strip renders (success path unchanged)', () => {
    renderSurface({ view: 'conversation', pttNotice: null })
    expect(screen.queryByText('Hold longer to record')).toBeNull()
    // A clean conversation has no status line at all (no notice of either kind).
    expect(screen.queryByRole('status')).toBeNull()
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
    const css = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), 'bar.css'),
      'utf8'
    )
    const body = css.match(/\.bar-surface\s*\{([^}]*)\}/)?.[1] ?? ''
    const overflow = body.match(/(?:^|[^-])overflow:\s*([a-z]+)/)?.[1]
    expect(overflow).toBe('clip')
  })
})
