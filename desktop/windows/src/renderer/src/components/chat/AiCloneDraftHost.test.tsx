// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, waitFor } from '@testing-library/react'
import type { AiCloneIncomingMessageEvent } from '../../../../shared/types'

const callAgentLLMSpy = vi.fn<(prompt: string) => Promise<string>>()
vi.mock('../../lib/agentLLM', () => ({ callAgentLLM: (prompt: string) => callAgentLLMSpy(prompt) }))

import { AiCloneDraftHost } from './AiCloneDraftHost'

let incomingCb: ((event: AiCloneIncomingMessageEvent) => void) | null
const submitDraftSpy = vi.fn().mockResolvedValue({ action: 'sent' })

const baseEvent: AiCloneIncomingMessageEvent = {
  chatID: 'chat-1',
  chatDisplayName: 'Jordan',
  mode: 'draft',
  incomingMessageText: 'are we still on for 6?',
  messageID: 'msg-1',
  messageTimestamp: 1_700_000_000_000,
  sessionGeneration: 0,
  promptText: 'system + user context here'
}

beforeEach(() => {
  vi.clearAllMocks()
  incomingCb = null
  ;(window as unknown as { omi: unknown }).omi = {
    onAiCloneIncomingMessage: (cb: (event: AiCloneIncomingMessageEvent) => void) => {
      incomingCb = cb
      return () => {
        incomingCb = null
      }
    },
    aiCloneSubmitDraft: submitDraftSpy
  }
})

afterEach(() => cleanup())

describe('AiCloneDraftHost', () => {
  it('renders nothing', () => {
    const { container } = render(<AiCloneDraftHost />)
    expect(container.firstChild).toBeNull()
  })

  it('drafts a reply via callAgentLLM and submits it back on an incoming message', async () => {
    callAgentLLMSpy.mockResolvedValue('sounds good, see you then!')
    render(<AiCloneDraftHost />)

    incomingCb?.(baseEvent)

    await waitFor(() => expect(submitDraftSpy).toHaveBeenCalledTimes(1))
    expect(callAgentLLMSpy).toHaveBeenCalledWith(baseEvent.promptText)
    expect(submitDraftSpy).toHaveBeenCalledWith({
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'are we still on for 6?',
      messageID: 'msg-1',
      messageTimestamp: 1_700_000_000_000,
      sessionGeneration: 0,
      draftText: 'sounds good, see you then!'
    })
  })

  it('still submits (with an empty draft) when the model returns nothing, so main can mark the message processed', async () => {
    callAgentLLMSpy.mockResolvedValue('   ')
    render(<AiCloneDraftHost />)

    incomingCb?.(baseEvent)

    await waitFor(() => expect(submitDraftSpy).toHaveBeenCalledTimes(1))
    expect(submitDraftSpy).toHaveBeenCalledWith(
      expect.objectContaining({ messageID: 'msg-1', draftText: '' })
    )
  })

  it('swallows a callAgentLLM failure instead of throwing', async () => {
    callAgentLLMSpy.mockRejectedValue(new Error('network down'))
    render(<AiCloneDraftHost />)

    incomingCb?.(baseEvent)

    await waitFor(() => expect(callAgentLLMSpy).toHaveBeenCalledTimes(1))
    expect(submitDraftSpy).not.toHaveBeenCalled()
  })

  it('unsubscribes on unmount', () => {
    const { unmount } = render(<AiCloneDraftHost />)
    expect(incomingCb).not.toBeNull()
    unmount()
    expect(incomingCb).toBeNull()
  })

  it('processes messages from the same chat sequentially, not concurrently', async () => {
    // The bug this closes: two messages in the same chat each trigger their
    // own independent LLM call. Without serialization, a faster call for
    // the SECOND (newer) message could reach aiCloneSubmitDraft before the
    // first message's still-in-flight call does, so a newer reply could get
    // sent before an older one — scrambling the conversation.
    let resolveA: ((value: string) => void) | undefined
    callAgentLLMSpy.mockImplementation((prompt: string) => {
      if (prompt === 'prompt-A') {
        return new Promise<string>((resolve) => {
          resolveA = resolve
        })
      }
      return Promise.resolve('reply-B')
    })

    render(<AiCloneDraftHost />)

    const eventA: AiCloneIncomingMessageEvent = {
      ...baseEvent,
      messageID: 'msg-A',
      promptText: 'prompt-A'
    }
    const eventB: AiCloneIncomingMessageEvent = {
      ...baseEvent,
      messageID: 'msg-B',
      promptText: 'prompt-B'
    }

    // A arrives first, B second — same chat.
    incomingCb?.(eventA)
    incomingCb?.(eventB)

    await waitFor(() => expect(callAgentLLMSpy).toHaveBeenCalledWith('prompt-A'))

    // A's model call hasn't resolved yet, so B — queued behind A for the
    // same chat — must not have started at all yet.
    expect(callAgentLLMSpy).not.toHaveBeenCalledWith('prompt-B')
    expect(submitDraftSpy).not.toHaveBeenCalled()

    resolveA?.('reply-A')

    // Wait for both to complete, then verify the ORDER — that's the actual
    // property under test. (B resolves near-instantly once unblocked, so
    // asserting an exact intermediate count of 1 here would be a race
    // against however fast the event loop drains microtasks, not a
    // meaningful check.)
    await waitFor(() => expect(submitDraftSpy).toHaveBeenCalledTimes(2))
    expect(submitDraftSpy).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ messageID: 'msg-A' })
    )
    expect(submitDraftSpy).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ messageID: 'msg-B' })
    )
  })

  it('does not block a message from a DIFFERENT chat while another chat is still processing', async () => {
    let resolveA: ((value: string) => void) | undefined
    callAgentLLMSpy.mockImplementation((prompt: string) => {
      if (prompt === 'prompt-A') {
        return new Promise<string>((resolve) => {
          resolveA = resolve
        })
      }
      return Promise.resolve('reply-other')
    })

    render(<AiCloneDraftHost />)

    const eventChat1: AiCloneIncomingMessageEvent = {
      ...baseEvent,
      chatID: 'chat-1',
      messageID: 'msg-A',
      promptText: 'prompt-A'
    }
    const eventChat2: AiCloneIncomingMessageEvent = {
      ...baseEvent,
      chatID: 'chat-2',
      messageID: 'msg-other',
      promptText: 'prompt-other'
    }

    incomingCb?.(eventChat1)
    incomingCb?.(eventChat2)

    // chat-2's message must not be stuck behind chat-1's still-pending call —
    // serialization is per chat, not global.
    await waitFor(() =>
      expect(submitDraftSpy).toHaveBeenCalledWith(
        expect.objectContaining({ messageID: 'msg-other' })
      )
    )

    resolveA?.('reply-A')
    await waitFor(() =>
      expect(submitDraftSpy).toHaveBeenCalledWith(expect.objectContaining({ messageID: 'msg-A' }))
    )
  })
})
