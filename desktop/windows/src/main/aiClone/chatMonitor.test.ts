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
    expect(result.latestMessageIds).toEqual(['2'])
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
    expect(result.latestMessageIds).toEqual(['2'])
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
    expect(result.latestMessageIds).toEqual([])
    expect(result.latestTimestamp).toBeUndefined()
  })

  it('records every message id sharing the newest timestamp, not just one', () => {
    // Two messages arriving in the same millisecond — a real possibility
    // (simultaneous sends, or a bridge with coarse timestamp resolution).
    const messages = [msg('1', false, 100), msg('2', false, 500), msg('3', false, 500)]
    const result = selectNewInboundMessages(messages, 50)
    expect(result.latestTimestamp).toBe(500)
    expect(result.latestMessageIds.sort()).toEqual(['2', '3'])
  })

  it('does not re-draft a message already seen at the exact cursor timestamp', () => {
    // Previous poll ended with the cursor at t=500, having already seen
    // both '2' and '3' at that timestamp. A naive `timestamp > cursor`
    // check can't express "seen already" vs "new" for ties — this must not
    // re-surface '2' or '3'.
    const messages = [msg('2', false, 500), msg('3', false, 500)]
    const result = selectNewInboundMessages(messages, 500, ['2', '3'])
    expect(result.newMessages).toEqual([])
  })

  it('surfaces a genuinely new message that happens to share the cursor timestamp', () => {
    // '2' was already seen at t=500 last time, but '4' is a new message
    // that (coincidentally) shares that exact timestamp — it must still be
    // drafted, not dropped just because it doesn't satisfy `timestamp >
    // lastSeenTimestamp`.
    const messages = [msg('2', false, 500), msg('4', false, 500)]
    const result = selectNewInboundMessages(messages, 500, ['2'])
    expect(result.newMessages.map((m) => m.id)).toEqual(['4'])
  })
})
