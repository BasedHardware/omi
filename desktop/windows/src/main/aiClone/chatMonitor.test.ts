import { describe, expect, it } from 'vitest'
import { selectNewInboundMessages, type BeeperMessageLike } from './chatMonitor'

const msg = (
  id: string,
  isSender: boolean,
  timestamp: number,
  text: string | undefined = 'hi'
): BeeperMessageLike => ({
  id,
  isSender,
  timestamp,
  text
})

describe('selectNewInboundMessages', () => {
  it('drafts nothing on the first-ever poll, but establishes the cursor', () => {
    const messages = [msg('1', false, 100), msg('2', true, 200)]
    const result = selectNewInboundMessages(messages, undefined)
    expect(result.newMessages).toEqual([])
    expect(result.latestMessageId).toBe('2')
    expect(result.latestTimestamp).toBe(200)
  })

  it('returns only inbound messages after the cursor, oldest first', () => {
    const messages = [
      msg('1', false, 100), // before cursor
      msg('2', false, 300),
      msg('3', true, 250), // own message, never drafted against
      msg('4', false, 200) // before cursor
    ]
    const result = selectNewInboundMessages(messages, 150)
    expect(result.newMessages.map((m) => m.id)).toEqual(['4', '2'])
  })

  it('advances the cursor past the newest message even if it is the user\u2019s own', () => {
    const messages = [msg('1', false, 100), msg('2', true, 500)]
    const result = selectNewInboundMessages(messages, 50)
    expect(result.latestMessageId).toBe('2')
    expect(result.latestTimestamp).toBe(500)
    expect(result.newMessages.map((m) => m.id)).toEqual(['1'])
  })

  it('skips empty/attachment-only messages (no text)', () => {
    const messages = [msg('1', false, 200, ''), { id: '2', isSender: false, timestamp: 300 }]
    const result = selectNewInboundMessages(messages, 100)
    expect(result.newMessages).toEqual([])
    expect(result.latestTimestamp).toBe(300)
  })

  it('handles an empty batch without throwing', () => {
    const result = selectNewInboundMessages([], 100)
    expect(result.newMessages).toEqual([])
    expect(result.latestMessageId).toBeUndefined()
    expect(result.latestTimestamp).toBeUndefined()
  })
})
