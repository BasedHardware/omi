import { describe, it, expect } from 'vitest'
import { nextStage, isPanelMode } from './hubStage'

describe('hubStage — the Hub stage machine', () => {
  it('goes to chat when the ask bar takes focus or a message is submitted', () => {
    expect(nextStage('hub', { type: 'askFocused' })).toBe('chat')
    expect(nextStage('hub', { type: 'submitted' })).toBe('chat')
    // A suggestion tap submits from the resting hub; Connect must not swallow it.
    expect(nextStage('connect', { type: 'submitted' })).toBe('chat')
  })

  it('toggles connect on and back off', () => {
    expect(nextStage('hub', { type: 'connectToggled' })).toBe('connect')
    expect(nextStage('connect', { type: 'connectToggled' })).toBe('hub')
    // From chat, Connect takes over the stage rather than returning to the hub.
    expect(nextStage('chat', { type: 'connectToggled' })).toBe('connect')
  })

  it('returns to the resting hub on Esc / click-outside, from any mode', () => {
    expect(nextStage('chat', { type: 'dismissed' })).toBe('hub')
    expect(nextStage('connect', { type: 'dismissed' })).toBe('hub')
    expect(nextStage('hub', { type: 'dismissed' })).toBe('hub')
  })

  it('treats every mode but the resting hub as a panel', () => {
    expect(isPanelMode('hub')).toBe(false)
    expect(isPanelMode('chat')).toBe(true)
    expect(isPanelMode('connect')).toBe(true)
  })
})
