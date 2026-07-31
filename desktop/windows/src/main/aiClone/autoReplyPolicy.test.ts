import { describe, expect, it } from 'vitest'
import { decideReplyAction, looksSensitive } from './autoReplyPolicy'

describe('decideReplyAction', () => {
  it('skips when the chat is off, regardless of draft content', () => {
    expect(decideReplyAction({ mode: 'off', draftText: 'sure, see you then!' })).toBe('skip')
  })

  it('skips a blank/whitespace-only draft', () => {
    expect(decideReplyAction({ mode: 'auto_send', draftText: '   ' })).toBe('skip')
  })

  it('always queues draft-mode chats for review', () => {
    expect(decideReplyAction({ mode: 'draft', draftText: 'sounds good!' })).toBe('queue_for_review')
  })

  it('sends an ordinary auto_send reply', () => {
    expect(decideReplyAction({ mode: 'auto_send', draftText: 'sounds good, see you at 6!' })).toBe(
      'send'
    )
  })

  it('downgrades a sensitive auto_send draft to review', () => {
    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: 'sure, I can wire transfer the deposit tonight'
      })
    ).toBe('queue_for_review')
  })

  it('always reviews a draft that flagged it needs input, even in auto_send', () => {
    expect(
      decideReplyAction({
        mode: 'auto_send',
        draftText: '[NEEDS_INPUT] not sure what time works',
        needsInput: true
      })
    ).toBe('queue_for_review')
  })
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
