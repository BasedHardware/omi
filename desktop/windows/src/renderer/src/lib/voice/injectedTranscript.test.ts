import { describe, it, expect } from 'vitest'
import { formatAssistantLine, shouldInjectIntoLive, ASSISTANT_SPEAKER } from './injectedTranscript'

describe('formatAssistantLine', () => {
  it('formats an utterance with the Omi speaker and a stable id', () => {
    const line = formatAssistantLine('Sure — I added that task.', 'u1')
    expect(line).toEqual({
      id: 'omi-voice-u1',
      speaker: ASSISTANT_SPEAKER,
      text: 'Sure — I added that task.'
    })
  })

  it('collapses streaming whitespace artifacts', () => {
    const line = formatAssistantLine('  Hello \n\n there,\t friend.  ', 'u2')
    expect(line?.text).toBe('Hello there, friend.')
  })

  it('returns null for empty/whitespace text (never appends blank lines)', () => {
    expect(formatAssistantLine('', 'u3')).toBe(null)
    expect(formatAssistantLine('   \n\t ', 'u4')).toBe(null)
  })

  it('same utterance id → same line id (upsert-safe across re-delivery)', () => {
    const a = formatAssistantLine('hi', 'turn-7')
    const b = formatAssistantLine('hi', 'turn-7')
    expect(a?.id).toBe(b?.id)
  })
})

describe('shouldInjectIntoLive', () => {
  it('injects only into a running record', () => {
    expect(shouldInjectIntoLive('live')).toBe(true)
    expect(shouldInjectIntoLive('connecting')).toBe(true)
    expect(shouldInjectIntoLive('idle')).toBe(false)
    expect(shouldInjectIntoLive('error')).toBe(false)
  })
})
