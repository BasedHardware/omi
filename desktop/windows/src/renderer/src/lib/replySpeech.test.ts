import { describe, expect, it, vi } from 'vitest'
import { createWebSpeechReplyPlayer, findReplySpeechBoundary } from './replySpeech'

describe('findReplySpeechBoundary', () => {
  it('waits until the first reply chunk is large enough', () => {
    expect(findReplySpeechBoundary('Too short.', { first: true })).toBeNull()
  })

  it('uses an early sentence boundary once the first chunk reaches the minimum', () => {
    const text = 'This is enough text to start speaking naturally now. More text follows'
    expect(findReplySpeechBoundary(text, { first: true })).toBe(52)
  })

  it('waits for preferred length before using clause boundaries', () => {
    const text = `${'a'.repeat(50)}, ${'b'.repeat(67)}`
    expect(findReplySpeechBoundary(text, { first: true })).toBeNull()
    expect(findReplySpeechBoundary(`${text} c`, { first: true })).toBe(51)
  })

  it('hard-cuts the first chunk at the emergency limit', () => {
    const text = 'a'.repeat(205)
    expect(findReplySpeechBoundary(text, { first: true })).toBe(200)
  })

  it('uses larger limits after the first spoken chunk', () => {
    expect(findReplySpeechBoundary(`${'a'.repeat(318)}.`, { first: false })).toBeNull()
    expect(findReplySpeechBoundary(`${'a'.repeat(320)}.`, { first: false })).toBe(321)
  })

  it('flushes any final leftover text', () => {
    expect(findReplySpeechBoundary('short final', { final: true, first: false })).toBe(11)
  })
})

describe('createWebSpeechReplyPlayer', () => {
  it('speaks a filler and replaces it with the first real reply chunk', () => {
    const speak = vi.fn()
    const cancel = vi.fn()
    class Utterance {
      text: string

      constructor(text: string) {
        this.text = text
      }
    }

    const player = createWebSpeechReplyPlayer({
      getWindow: () =>
        ({
          speechSynthesis: { speak, cancel },
          SpeechSynthesisUtterance: Utterance
        }) as unknown as Window,
      fillerText: 'Checking.'
    })

    player.startFiller()
    expect(speak.mock.calls[0][0].text).toBe('Checking.')

    expect(player.speak('  Hello\nworld.  ')).toBe(true)
    expect(cancel).toHaveBeenCalledTimes(2)
    expect(speak.mock.calls[1][0].text).toBe('Hello world.')
  })

  it('no-ops when Web Speech is unavailable', () => {
    const player = createWebSpeechReplyPlayer({ getWindow: () => undefined })
    expect(player.speak('Hello')).toBe(false)
    expect(() => player.startFiller()).not.toThrow()
    expect(() => player.cancel()).not.toThrow()
  })
})
