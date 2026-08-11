import { describe, expect, it } from 'vitest'
import { decideReplyAction, isValidChatMode, looksSensitive } from './autoReplyPolicy'

describe('decideReplyAction', () => {
  it('skips when the chat is off, regardless of draft content', () => {
    expect(
      decideReplyAction({
        mode: 'off',
        draftText: 'sure, see you then!',
        incomingMessageText: 'hi'
      })
    ).toBe('skip')
  })

  it('skips a blank/whitespace-only draft', () => {
    expect(
      decideReplyAction({ mode: 'auto_send', draftText: '   ', incomingMessageText: 'hi' })
    ).toBe('skip')
  })

  it('always queues draft-mode chats for review', () => {
    expect(
      decideReplyAction({ mode: 'draft', draftText: 'sounds good!', incomingMessageText: 'hi' })
    ).toBe('queue_for_review')
  })

  it('sends an ordinary auto_send reply', () => {
    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: 'sounds good, see you at 6!',
        incomingMessageText: 'are we still on for 6?'
      })
    ).toBe('send')
  })

  it('downgrades a sensitive auto_send draft to review', () => {
    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: 'sure, I can wire transfer the deposit tonight',
        incomingMessageText: 'can you send the deposit?'
      })
    ).toBe('queue_for_review')
  })

  it('downgrades to review when the INCOMING message is sensitive, even if the draft is a bland agreement', () => {
    // The actual bug this closes: a short "sounds good" style reply contains
    // no sensitive keywords of its own, but if it's agreeing to something
    // the incoming message asked for, auto-sending it is exactly as risky
    // as if the draft had spelled the commitment out itself.
    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: 'sounds good!',
        incomingMessageText: 'can you wire transfer the deposit tonight?'
      })
    ).toBe('queue_for_review')

    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: 'I agree',
        incomingMessageText: "let's finally get that divorce"
      })
    ).toBe('queue_for_review')
  })

  it('still sends when neither the draft nor the incoming message is sensitive', () => {
    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: 'sounds good!',
        incomingMessageText: 'want to grab lunch tomorrow?'
      })
    ).toBe('send')
  })

  it('always reviews a draft that flagged it needs input, even in auto_send', () => {
    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: '[NEEDS_INPUT] not sure what time works',
        incomingMessageText: 'want to meet up sometime?',
        needsInput: true
      })
    ).toBe('queue_for_review')
  })

  it('fails closed to skip for an unrecognized mode value, never falls through to send', () => {
    // Simulates a corrupted settings file or a stale caller handing this an
    // arbitrary string at runtime — TS's ChatReplyMode type doesn't stop
    // this from happening outside a fully-typed call site.
    const corrupted = {
      mode: 'AUTO_SEND',
      draftText: 'sounds good!',
      incomingMessageText: 'hi'
    } as unknown as Parameters<typeof decideReplyAction>[0]
    expect(decideReplyAction(corrupted)).toBe('skip')
  })

  it('fails closed to skip for an empty-string mode', () => {
    const corrupted = {
      mode: '',
      draftText: 'sounds good!',
      incomingMessageText: 'hi'
    } as unknown as Parameters<typeof decideReplyAction>[0]
    expect(decideReplyAction(corrupted)).toBe('skip')
  })
})

describe('isValidChatMode', () => {
  it.each(['off', 'draft', 'auto_send'])('accepts %s', (mode) => {
    expect(isValidChatMode(mode)).toBe(true)
  })

  it.each([undefined, null, 42, {}, [], '', 'AUTO_SEND', 'send', 'auto-send'])(
    'rejects %j',
    (value) => {
      expect(isValidChatMode(value)).toBe(false)
    }
  )
})

describe('looksSensitive', () => {
  it.each([
    'can you send your bank account number',
    "I'm thinking of breaking up with him",
    'the doctor gave me a diagnosis today',
    'I got laid off this morning'
  ])('flags: %s', (text) => {
    expect(looksSensitive(text)).toBe(true)
  })

  it('does not flag ordinary chat', () => {
    expect(looksSensitive('want to grab lunch tomorrow?')).toBe(false)
  })
})
