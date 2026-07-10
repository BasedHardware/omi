import { describe, it, expect } from 'vitest'
import {
  passThroughClassifier,
  verdictIsCapturable,
  type SpeechMusicClassifier,
  type SpeechMusicVerdict
} from './loopbackClassifier'

describe('passThroughClassifier', () => {
  it('classifies any window as speech (v1 capture-everything default)', () => {
    expect(passThroughClassifier.classify(new Int16Array([0, 1, 2, 3]))).toBe('speech')
    expect(passThroughClassifier.classify(new Int16Array(0))).toBe('speech')
  })
})

describe('verdictIsCapturable', () => {
  it('skips only a confident music verdict', () => {
    expect(verdictIsCapturable('music')).toBe(false)
  })

  it('captures speech and captures on uncertainty (fail-open)', () => {
    expect(verdictIsCapturable('speech')).toBe(true)
    expect(verdictIsCapturable('unknown')).toBe(true)
  })

  it('a future classifier returning music is honored by the gate semantic', () => {
    // Stands in for the Phase-5 MediaPipe classifier: the seam types + semantic are
    // wired so only this module changes when a real model lands.
    const musicOnly: SpeechMusicClassifier = { classify: (): SpeechMusicVerdict => 'music' }
    expect(verdictIsCapturable(musicOnly.classify(new Int16Array(8)))).toBe(false)
  })
})
