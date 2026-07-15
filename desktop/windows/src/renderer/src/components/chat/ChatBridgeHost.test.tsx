// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'
import type { BarChatState } from '../../../../shared/types'
import type { ChatMsg } from '../../hooks/useChat'

// ChatBridgeHost is the main-window half of the bar↔main chat bridge: it drives
// the ONE chat engine when the bar sends, and broadcasts projected state back to
// the bar. Mock the engine (useAppState) + the IPC bridge (window.omi) and assert
// the contract that kills the duplicate-useChat continuity bug (C3).

const sendSpy = vi.fn(() => Promise.resolve())
let chat = {
  history: [] as ChatMsg[],
  sending: false,
  speaking: false,
  agentActive: false,
  send: sendSpy,
  reset: vi.fn()
}
vi.mock('../../state/appState', () => ({ useAppState: () => ({ chat }) }))

const speakSpy = vi.fn((_text: string) => Promise.resolve())
vi.mock('../../lib/voice/voiceController', () => ({
  interruptCurrentResponse: vi.fn(),
  speakText: (text: string) => speakSpy(text)
}))

import { ChatBridgeHost } from './ChatBridgeHost'
import { onUsageLimit, dismissUsageLimit, type UsageLimitReason } from '../../lib/usageLimit'

let barSendCb: ((p: { text: string; fromVoice: boolean }) => void) | null
let reqStateCb: (() => void) | null
let usageLimitCb: ((p: { message: string; spoken: boolean; popup?: boolean }) => void) | null
let published: BarChatState[]

beforeEach(() => {
  vi.clearAllMocks()
  barSendCb = null
  reqStateCb = null
  usageLimitCb = null
  published = []
  dismissUsageLimit()
  chat = {
    history: [],
    sending: false,
    speaking: false,
    agentActive: false,
    send: sendSpy,
    reset: vi.fn()
  }
  ;(window as unknown as { omi: unknown }).omi = {
    onBarChatSend: (cb: (p: { text: string; fromVoice: boolean }) => void) => {
      barSendCb = cb
      return () => {}
    },
    onBarRequestChatState: (cb: () => void) => {
      reqStateCb = cb
      return () => {}
    },
    onBarUsageLimit: (cb: (p: { message: string; spoken: boolean; popup?: boolean }) => void) => {
      usageLimitCb = cb
      return () => {}
    },
    publishChatState: (s: BarChatState) => published.push(s)
  }
})
afterEach(() => cleanup())

const settle = (): Promise<void> => act(async () => await new Promise((r) => setTimeout(r, 70)))

describe('ChatBridgeHost', () => {
  it('drives the ONE chat.send() when the bar sends — threading fromVoice', async () => {
    render(<ChatBridgeHost />)
    barSendCb?.({ text: 'what is next', fromVoice: true })
    await settle()
    expect(sendSpy).toHaveBeenCalledWith('what is next', { fromVoice: true })
  })

  it('defers a bar send while the engine is busy, then delivers it when idle (no cross-surface drop)', async () => {
    // Engine already streaming a Home-initiated reply.
    chat = { ...chat, sending: true }
    const { rerender } = render(<ChatBridgeHost />)
    barSendCb?.({ text: 'spoken while busy', fromVoice: true })
    await settle()
    // Busy → the bar/PTT message is QUEUED, not dropped by useChat's re-entrancy
    // latch, and not delivered yet.
    expect(sendSpy).not.toHaveBeenCalled()
    // Engine goes idle → the queued send is delivered (against the latest send).
    chat = { ...chat, sending: false }
    rerender(<ChatBridgeHost />)
    await settle()
    expect(sendSpy).toHaveBeenCalledWith('spoken while busy', { fromVoice: true })
  })

  it('publishes the projected state to the bar on mount (idle)', () => {
    render(<ChatBridgeHost />)
    expect(published[0]).toEqual({
      messages: [],
      sending: false,
      status: 'idle',
      agentsActive: false
    })
  })

  it('projects streaming → sending and TTS playback → speaking', async () => {
    const { rerender } = render(<ChatBridgeHost />)
    published.length = 0
    chat = { ...chat, sending: true }
    rerender(<ChatBridgeHost />)
    await settle()
    expect(published.at(-1)).toMatchObject({ sending: true, status: 'sending' })

    published.length = 0
    chat = { ...chat, sending: false, speaking: true }
    rerender(<ChatBridgeHost />)
    await settle()
    expect(published.at(-1)).toMatchObject({ status: 'speaking' })
  })

  it('answers a pull (bar:requestChatState) with the current snapshot', () => {
    chat = {
      ...chat,
      history: [{ id: 'u1', role: 'user', content: 'hi' }]
    }
    render(<ChatBridgeHost />)
    published.length = 0
    reqStateCb?.()
    expect(published.at(-1)).toEqual({
      messages: [{ id: 'u1', role: 'user', content: 'hi' }],
      sending: false,
      status: 'idle',
      agentsActive: false
    })
  })

  it('does NOT truncate a long agent task — a bar send stays queued past the ordinary cap, then delivers', async () => {
    // A coding-agent task holds the engine busy for minutes. Before the fix, the
    // 15s idle-wait cap fired mid-task and the deferred send hit useChat's private
    // re-entrancy latch → silently dropped (the Major regression this guards).
    vi.useFakeTimers()
    try {
      chat = { ...chat, sending: true, agentActive: true }
      const { rerender } = render(<ChatBridgeHost />)
      barSendCb?.({ text: 'queued during agent task', fromVoice: false })
      // Advance WELL past both the old 15s cap and the 60s ordinary-stream cap.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(90_000)
      })
      // agentActive exempts the task from the cap → still queued, not dropped.
      expect(sendSpy).not.toHaveBeenCalled()
      // Agent finishes → engine idle → the queued send finally delivers.
      chat = { ...chat, sending: false, agentActive: false }
      rerender(<ChatBridgeHost />)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100)
      })
      expect(sendSpy).toHaveBeenCalledWith('queued during agent task', { fromVoice: false })
    } finally {
      vi.useRealTimers()
    }
  })

  it('bounds an ordinary wedged stream — the cap fires so the bar queue never blocks forever', async () => {
    // A NON-agent send that never clears (wedged SSE) must not block the bar's
    // send queue indefinitely: the cap fires (with a warning) and the queued send
    // is delivered best-effort rather than lost or stuck.
    vi.useFakeTimers()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      chat = { ...chat, sending: true, agentActive: false }
      render(<ChatBridgeHost />)
      barSendCb?.({ text: 'behind a wedged stream', fromVoice: false })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(61_000)
      })
      expect(sendSpy).toHaveBeenCalledWith('behind a wedged stream', { fromVoice: false })
      expect(warn).toHaveBeenCalled()
    } finally {
      warn.mockRestore()
      vi.useRealTimers()
    }
  })

  it('raises the shared usage-limit popup when a bar send was blocked by the quota', () => {
    // The bar is a separate renderer: it cannot show UsageLimitPopup (mounted in
    // the main window) — so a blocked bar send hops here and we raise it.
    const reasons: (UsageLimitReason | null)[] = []
    const unsub = onUsageLimit((r) => reasons.push(r))
    render(<ChatBridgeHost />)

    usageLimitCb?.({ message: "You've reached 30 Free messages this month.", spoken: false })

    expect(reasons.at(-1)).toBe('chat')
    // A typed block is shown, not spoken.
    expect(speakSpy).not.toHaveBeenCalled()
    unsub()
  })

  it('speaks the limit line back for a blocked VOICE turn, but does NOT re-pop the popup (popup:false)', () => {
    // A blocked voice send arrives with popup:false: the pre-capture PTT veto
    // already owns the modal for voice (macOS parity). TTS lives here
    // (voiceController), so the turn is still answered aloud — but the popup must
    // NOT be raised a second time.
    const reasons: (UsageLimitReason | null)[] = []
    const unsub = onUsageLimit((r) => reasons.push(r))
    render(<ChatBridgeHost />)
    usageLimitCb?.({
      message: "You've reached your monthly free message limit.",
      spoken: true,
      popup: false
    })

    expect(speakSpy).toHaveBeenCalledWith("You've reached your monthly free message limit.")
    expect(reasons).not.toContain('chat')
    unsub()
  })
})
