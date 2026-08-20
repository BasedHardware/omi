import { describe, it, expect } from 'vitest'
import { decide, type ResponderInput } from './responder'

const base = (over: Partial<ResponderInput> = {}): ResponderInput => ({
  message: {
    id: 'm1',
    chatID: 'c1',
    text: 'where are you from?',
    senderName: 'Alice',
    isSender: false,
    timestamp: 2_000
  },
  chatType: 'single',
  chatMode: 'draft',
  sessionStartedAt: 1_000,
  autoSentThisHour: 0,
  autoSendHourlyCap: 30,
  ...over
})

describe('decide', () => {
  it('drafts an incoming DM when the chat is in draft mode', () => {
    expect(decide(base())).toEqual({ action: 'draft' })
  })

  it('downgrades a legacy auto chat to a reviewable draft', () => {
    expect(decide(base({ chatMode: 'auto' }))).toEqual({ action: 'draft' })
  })

  it('ignores chats that are off', () => {
    expect(decide(base({ chatMode: 'off' }))).toEqual({ action: 'ignore', reason: 'chat_off' })
  })

  it('ignores the user’s own outgoing messages (no self-reply loop)', () => {
    const input = base({ chatMode: 'auto' })
    input.message.isSender = true
    expect(decide(input)).toEqual({ action: 'ignore', reason: 'own_message' })
  })

  it('ignores messages that predate the listening session', () => {
    const input = base()
    input.message.timestamp = 500
    expect(decide(input)).toEqual({ action: 'ignore', reason: 'old_message' })
  })

  it('ignores messages whose timestamp cannot prove they are from this session', () => {
    // Reconnect backfill without a usable timestamp used to skip the cutoff
    // entirely and draft replies to history.
    for (const timestamp of [undefined, 'not-a-date']) {
      const input = base()
      input.message.timestamp = timestamp
      expect(decide(input)).toEqual({ action: 'ignore', reason: 'undated_message' })
    }
  })

  it('ignores deleted and non-text messages', () => {
    const deleted = base()
    deleted.message.isDeleted = true
    expect(decide(deleted)).toEqual({ action: 'ignore', reason: 'deleted' })

    const empty = base()
    empty.message.text = '   '
    expect(decide(empty)).toEqual({ action: 'ignore', reason: 'non_text' })
  })
})
