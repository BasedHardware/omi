import { describe, it, expect } from 'vitest'
import {
  passThroughClassifier,
  verdictIsCapturable,
  verdictFromLabel,
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

describe('verdictFromLabel (YAMNet/AudioSet label mapping)', () => {
  it('maps confident speech-family labels to speech', () => {
    expect(verdictFromLabel('Speech', 0.9)).toBe('speech')
    expect(verdictFromLabel('Conversation', 0.7)).toBe('speech')
    expect(verdictFromLabel('Narration, monologue', 0.6)).toBe('speech')
  })

  it('maps confident music-family labels to music', () => {
    expect(verdictFromLabel('Music', 0.9)).toBe('music')
    expect(verdictFromLabel('Singing', 0.8)).toBe('music')
    expect(verdictFromLabel('Musical instrument', 0.7)).toBe('music')
  })

  it('speech hints win over music hints ("Music of speech" style overlaps)', () => {
    expect(verdictFromLabel('Speech synthesizer music', 0.9)).toBe('speech')
  })

  it('low confidence and unrelated labels are unknown (fail-open)', () => {
    expect(verdictFromLabel('Music', 0.3)).toBe('unknown') // below threshold
    expect(verdictFromLabel('Dog', 0.95)).toBe('unknown')
    expect(verdictFromLabel('', 0.99)).toBe('unknown')
  })
})
