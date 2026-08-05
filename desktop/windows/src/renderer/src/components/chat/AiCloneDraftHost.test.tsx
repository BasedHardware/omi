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
})
