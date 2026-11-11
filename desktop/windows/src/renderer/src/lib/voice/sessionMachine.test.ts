import { describe, it, expect } from 'vitest'
import {
  initialVoiceState,
  transition,
  type VoiceSessionState,
  type VoiceSessionEvent
} from './sessionMachine'

function run(events: VoiceSessionEvent[], from: VoiceSessionState = initialVoiceState) {
  return events.reduce(transition, from)
}

describe('voice session machine', () => {
  it('happy path: idle → connecting → live → idle', () => {
    let s = transition(initialVoiceState, { type: 'start', provider: 'openai' })
    expect(s).toEqual({ status: 'connecting', provider: 'openai' })
    s = transition(s, { type: 'connected' })
    expect(s).toEqual({ status: 'live', provider: 'openai', muted: false })
    s = transition(s, { type: 'stop' })
    expect(s).toEqual({ status: 'idle' })
  })

  it('mint fallback changes the provider while connecting', () => {
    const s = run([
      { type: 'start', provider: 'openai' },
      { type: 'provider-changed', provider: 'gemini' },
      { type: 'connected' }
    ])
    expect(s).toEqual({ status: 'live', provider: 'gemini', muted: false })
  })

  it('provider-changed is ignored outside connecting', () => {
    const live = run([{ type: 'start', provider: 'openai' }, { type: 'connected' }])
    expect(transition(live, { type: 'provider-changed', provider: 'gemini' })).toBe(live)
  })

  it('failure lands in error with retryability, and error can restart', () => {
    let s = run([
      { type: 'start', provider: 'openai' },
      { type: 'fail', message: 'mint failed (503)', retryable: true }
    ])
    expect(s).toEqual({ status: 'error', message: 'mint failed (503)', retryable: true })
    s = transition(s, { type: 'start', provider: 'gemini' })
    expect(s).toEqual({ status: 'connecting', provider: 'gemini' })
  })

  it('a mid-session fatal drop moves live → error', () => {
    const s = run([
      { type: 'start', provider: 'gemini' },
      { type: 'connected' },
      { type: 'fail', message: 'socket dropped', retryable: true }
    ])
    expect(s).toEqual({ status: 'error', message: 'socket dropped', retryable: true })
  })

  it('a late fail after stop does NOT resurrect the error surface', () => {
    const s = run([
      { type: 'start', provider: 'openai' },
      { type: 'stop' },
      { type: 'fail', message: 'late teardown error', retryable: true }
    ])
    expect(s).toEqual({ status: 'idle' })
  })

  it('start is a no-op while connecting or live (double-click guard)', () => {
    const connecting = transition(initialVoiceState, { type: 'start', provider: 'openai' })
    expect(transition(connecting, { type: 'start', provider: 'gemini' })).toBe(connecting)
    const live = transition(connecting, { type: 'connected' })
    expect(transition(live, { type: 'start', provider: 'gemini' })).toBe(live)
  })

  it('mute toggles only while live', () => {
    const live = run([{ type: 'start', provider: 'openai' }, { type: 'connected' }])
    expect(transition(live, { type: 'set-muted', muted: true })).toEqual({
      status: 'live',
      provider: 'openai',
      muted: true
    })
    expect(transition(initialVoiceState, { type: 'set-muted', muted: true })).toBe(
      initialVoiceState
    )
  })

  it('connected is ignored when not connecting (late handshake after stop)', () => {
    expect(transition(initialVoiceState, { type: 'connected' })).toBe(initialVoiceState)
  })
})
