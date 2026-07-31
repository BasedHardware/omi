import { describe, expect, it } from 'vitest'
import { buildDraftPrompt, draftNeedsInput } from './personaDraftPrompt'

describe('buildDraftPrompt', () => {
  it('includes the persona, history, and incoming message in the user turn', () => {
    const [system, user] = buildDraftPrompt({
      personaProfileText: '- Works at Acme as an engineer',
      chatDisplayName: 'Jordan',
      history: [{ senderName: 'Jordan', text: 'hey are we still on for 6?', isSelf: false }],
      incomingMessage: { senderName: 'Jordan', text: 'lmk if that still works', isSelf: false }
    })
    expect(system.role).toBe('system')
    expect(user.role).toBe('user')
    expect(user.content).toContain('Acme')
    expect(user.content).toContain('Jordan: hey are we still on for 6?')
    expect(user.content).toContain('lmk if that still works')
  })

  it('falls back gracefully with no profile yet', () => {
    const [, user] = buildDraftPrompt({
      personaProfileText: null,
      chatDisplayName: 'Sam',
      history: [],
      incomingMessage: { senderName: 'Sam', text: 'hi!', isSelf: false }
    })
    expect(user.content).toContain('No profile information is available yet')
  })

  it('labels the user’s own prior messages as "User" in history', () => {
    const [, user] = buildDraftPrompt({
      personaProfileText: null,
      chatDisplayName: 'Sam',
      history: [{ senderName: 'ignored', text: 'sure, sounds good', isSelf: true }],
      incomingMessage: { senderName: 'Sam', text: 'great, see you then', isSelf: false }
    })
    expect(user.content).toContain('User: sure, sounds good')
  })
})

describe('draftNeedsInput', () => {
  it('detects the [NEEDS_INPUT] marker', () => {
    expect(draftNeedsInput('[NEEDS_INPUT] not sure what time')).toBe(true)
  })

  it('is false for an ordinary draft', () => {
    expect(draftNeedsInput('sounds good, see you then!')).toBe(false)
  })
})
