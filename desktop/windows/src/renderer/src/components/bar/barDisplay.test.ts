import { describe, it, expect } from 'vitest'
import { deriveOrbState, isBarBusy, omiChatListStatus } from './barDisplay'
import type { BarChatState } from '../../../../shared/types'

const chat = (partial: Partial<BarChatState> = {}): BarChatState => ({
  messages: [],
  sending: false,
  status: 'idle',
  ...partial
})

describe('deriveOrbState', () => {
  const base = {
    recording: false,
    transcribing: false,
    status: 'idle',
    continuousListening: false,
    agentsActive: false
  } as const

  it('recording → speaking WITH the user amplitude (the blob reacts to the mic)', () => {
    expect(deriveOrbState({ ...base, recording: true })).toEqual({
      state: 'speaking',
      withAmplitude: true
    })
  })

  it('recording wins even while a reply is still speaking/streaming', () => {
    expect(deriveOrbState({ ...base, recording: true, status: 'speaking' }).withAmplitude).toBe(
      true
    )
    expect(deriveOrbState({ ...base, recording: true, status: 'sending' }).state).toBe('speaking')
  })

  it('TTS playback → speaking WITHOUT amplitude (Omi is talking)', () => {
    expect(deriveOrbState({ ...base, status: 'speaking' })).toEqual({
      state: 'speaking',
      withAmplitude: false
    })
  })

  it('streaming/finalizing → thinking', () => {
    expect(deriveOrbState({ ...base, status: 'sending' }).state).toBe('thinking')
    expect(deriveOrbState({ ...base, transcribing: true }).state).toBe('thinking')
  })

  it('continuous listening → listening; otherwise idle', () => {
    expect(deriveOrbState({ ...base, continuousListening: true }).state).toBe('listening')
    expect(deriveOrbState(base).state).toBe('idle')
  })

  it('running coding-agent → agents pose (over generic thinking; both are status=sending)', () => {
    expect(deriveOrbState({ ...base, agentsActive: true, status: 'sending' })).toEqual({
      state: 'agents',
      withAmplitude: false
    })
    // agents also wins over passive continuous listening
    expect(deriveOrbState({ ...base, agentsActive: true, continuousListening: true }).state).toBe(
      'agents'
    )
  })

  it('live voice still wins over an active agent (user turn is most salient)', () => {
    // user holding PTT during an agent task → the user's reactive mic turn
    expect(deriveOrbState({ ...base, agentsActive: true, recording: true })).toEqual({
      state: 'speaking',
      withAmplitude: true
    })
    // Omi speaking a reply also outranks the agents pose
    expect(deriveOrbState({ ...base, agentsActive: true, status: 'speaking' }).state).toBe(
      'speaking'
    )
  })
})

describe('isBarBusy (pill retract-hold)', () => {
  it('holds the pill open during recording / finalizing / streaming / speaking', () => {
    expect(isBarBusy({ recording: true, transcribing: false, status: 'idle' })).toBe(true)
    expect(isBarBusy({ recording: false, transcribing: true, status: 'idle' })).toBe(true)
    expect(isBarBusy({ recording: false, transcribing: false, status: 'sending' })).toBe(true)
    expect(isBarBusy({ recording: false, transcribing: false, status: 'speaking' })).toBe(true)
  })

  it('is idle when nothing is in flight (the pill may retract)', () => {
    expect(isBarBusy({ recording: false, transcribing: false, status: 'idle' })).toBe(false)
  })
})

describe('omiChatListStatus', () => {
  it('reflects the live activity first', () => {
    expect(omiChatListStatus(chat({ status: 'speaking' }))).toBe('Speaking…')
    expect(omiChatListStatus(chat({ status: 'sending' }))).toBe('Thinking…')
  })

  it('previews the last turn (prefixing the user’s own line)', () => {
    expect(
      omiChatListStatus(chat({ messages: [{ role: 'assistant', content: 'Here is the answer' }] }))
    ).toBe('Here is the answer')
    expect(omiChatListStatus(chat({ messages: [{ role: 'user', content: 'what is next' }] }))).toBe(
      'You: what is next'
    )
  })

  it('collapses whitespace so a multi-line reply stays one line', () => {
    expect(
      omiChatListStatus(chat({ messages: [{ role: 'assistant', content: 'a\n\n  b   c' }] }))
    ).toBe('a b c')
  })

  it('invites when the thread is empty', () => {
    expect(omiChatListStatus(chat())).toBe('Ask me anything')
  })
})
