// @vitest-environment jsdom
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import type { ChatMsg } from '../../hooks/useChat'

// Regression guard for the chat-input lag fix (perf(windows/chat)).
//
// The bug: the composer draft lives in a common ANCESTOR of both the text input
// and the message transcript (HomeHub owns `input`; BarApp owns `draft`). Before
// the fix, ChatMessages rendered every bubble inline, so each keystroke
// re-rendered — and re-parsed the markdown of — every settled message in the
// thread. Measured cost on a 24-message thread: 24ms/keystroke of pure scripting
// vs 0.02ms for the bar's transcript-less top input (same machine), which is the
// lag + "backspace deletes in chunks" the report describes.
//
// The fix memoizes each message row (ChatMessages → memo'd MessageRow), so a
// keystroke that changes only the ancestor's draft re-renders zero settled rows.
// This test counts real markdown renders through the memo boundary: `Markdown`
// (the leaf that does the per-message parse) is stubbed with a render counter, so
// an increment means a message actually re-rendered.

// vi.hoisted so the counter exists before the hoisted vi.mock factory runs.
const markdownRenders = vi.hoisted(() => vi.fn())
vi.mock('../Markdown', () => ({
  Markdown: ({ text }: { text: string }) => {
    markdownRenders(text)
    return <div data-testid="md">{text}</div>
  }
}))

import { ChatMessages } from './ChatMessages'

afterEach(cleanup)
beforeEach(() => markdownRenders.mockClear())

function transcript(pairs: number): ChatMsg[] {
  const out: ChatMsg[] = []
  for (let i = 0; i < pairs; i++) {
    out.push({ id: `u${i}`, role: 'user', content: `question ${i}` })
    out.push({ id: `a${i}`, role: 'assistant', content: `answer **${i}** with \`code\`` })
  }
  return out
}

// Mirrors the real structure: a draft ancestor that renders BOTH the input and
// the transcript. `sending=false` (a settled thread) so every row is memoizable.
function ChatInputSurface({ messages }: { messages: ChatMsg[] }): React.JSX.Element {
  const [draft, setDraft] = useState('')
  return (
    <div>
      <input data-testid="composer" value={draft} onChange={(e) => setDraft(e.target.value)} />
      <ChatMessages messages={messages} sending={false} variant="main" />
    </div>
  )
}

describe('ChatMessages per-keystroke re-render (perf regression)', () => {
  it('typing in the composer re-renders ZERO settled message rows', () => {
    const msgs = transcript(12) // 12 assistant bubbles → 12 markdown renders on mount
    const { getByTestId } = render(<ChatInputSurface messages={msgs} />)

    const afterMount = markdownRenders.mock.calls.length
    expect(afterMount).toBe(12) // one parse per assistant message, once

    // Type 20 characters. Before the fix this re-rendered all 12 bubbles per
    // keystroke (240 extra markdown renders); after the fix the memo boundary
    // bails on every settled row.
    let s = ''
    for (let i = 0; i < 20; i++) {
      s += 'a'
      fireEvent.change(getByTestId('composer'), { target: { value: s } })
    }

    const duringTyping = markdownRenders.mock.calls.length - afterMount
    expect(duringTyping).toBe(0)
  })

  it('only the message whose object changed re-renders (memo not over-eager)', () => {
    // As a reply streams, useChat.writeAssistant replaces THAT message with a
    // fresh object each tick while every settled message keeps its reference.
    // The memo must therefore re-render exactly the changed row and bail on the
    // rest — otherwise the live reply would freeze. Drive that reference swap
    // directly (sending=false keeps every row on the immediate, timer-free
    // markdown path so the count is deterministic).
    // The settled message keeps a STABLE reference across renders (as useChat
    // does — only the streaming reply is replaced with a fresh object); only the
    // live message gets a new object per revision.
    const settled: ChatMsg = { id: 'a0', role: 'assistant', content: 'settled answer' }
    function Swapper(): React.JSX.Element {
      const [rev, setRev] = useState(0)
      const msgs: ChatMsg[] = [
        settled,
        { id: 'live', role: 'assistant', content: `live rev ${rev}` }
      ]
      return (
        <div>
          <button data-testid="grow" onClick={() => setRev((r) => r + 1)}>
            grow
          </button>
          <ChatMessages messages={msgs} sending={false} variant="main" />
        </div>
      )
    }
    const { getByTestId } = render(<Swapper />)
    const afterMount = markdownRenders.mock.calls.length
    expect(afterMount).toBe(2) // both bubbles parse once on mount

    fireEvent.click(getByTestId('grow'))
    fireEvent.click(getByTestId('grow'))

    // The core memo guarantee: EVERY re-parse after mount belongs to the row
    // whose object changed — the settled bubble (unchanged reference) is never
    // among them — and the changed row DID re-parse (the live reply isn't frozen).
    // The exact per-change render count is env-sensitive (dev double-invoke), so
    // assert the invariant, not the multiplier.
    const live = markdownRenders.mock.calls.slice(afterMount)
    expect(live.length).toBeGreaterThanOrEqual(2)
    expect(live.every(([text]) => String(text).startsWith('live rev'))).toBe(true)
    expect(live.some(([text]) => text === 'live rev 2')).toBe(true)
  })

  it('appending a turn re-renders the isLast-flipped and new rows, never the untouched settled ones', () => {
    // Guards the memo-sensitive `isLast` transition: appending a message flips
    // the previously-last row's isLast true→false (so it must re-render) while
    // an earlier settled row (stable reference, isLast already false) must bail —
    // proving the memo neither drops the needed update nor re-runs the rest.
    const first: ChatMsg = { id: 'a0', role: 'assistant', content: 'first answer' }
    const second: ChatMsg = { id: 'a1', role: 'assistant', content: 'second answer' }
    function Appender(): React.JSX.Element {
      const [extra, setExtra] = useState(false)
      const msgs = extra
        ? [first, second, { id: 'a2', role: 'assistant' as const, content: 'third answer' }]
        : [first, second]
      return (
        <div>
          <button data-testid="add" onClick={() => setExtra(true)}>
            add
          </button>
          <ChatMessages messages={msgs} sending={false} variant="main" />
        </div>
      )
    }
    const { getByTestId } = render(<Appender />)
    const afterMount = markdownRenders.mock.calls.length
    expect(afterMount).toBe(2)

    fireEvent.click(getByTestId('add'))

    const after = markdownRenders.mock.calls.slice(afterMount).map(([t]) => t)
    // The new row parses; the previously-last row (isLast flipped) re-renders;
    // the untouched first row (stable ref, isLast unchanged) never re-parses.
    expect(after).toContain('third answer')
    expect(after).toContain('second answer')
    expect(after).not.toContain('first answer')
  })
})
