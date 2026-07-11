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
  send: sendSpy,
  reset: vi.fn()
}
vi.mock('../../state/appState', () => ({ useAppState: () => ({ chat }) }))

import { ChatBridgeHost } from './ChatBridgeHost'

let barSendCb: ((p: { text: string; fromVoice: boolean }) => void) | null
let reqStateCb: (() => void) | null
let published: BarChatState[]

beforeEach(() => {
  vi.clearAllMocks()
  barSendCb = null
  reqStateCb = null
  published = []
  chat = { history: [], sending: false, speaking: false, send: sendSpy, reset: vi.fn() }
  ;(window as unknown as { omi: unknown }).omi = {
    onBarChatSend: (cb: (p: { text: string; fromVoice: boolean }) => void) => {
      barSendCb = cb
      return () => {}
    },
    onBarRequestChatState: (cb: () => void) => {
      reqStateCb = cb
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

  it('publishes the projected state to the bar on mount (idle)', () => {
    render(<ChatBridgeHost />)
    expect(published[0]).toEqual({ messages: [], sending: false, status: 'idle' })
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
      status: 'idle'
    })
  })
})
