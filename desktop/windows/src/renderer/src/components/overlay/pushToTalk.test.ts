import { describe, it, expect } from 'vitest'
import {
  isHold,
  assembleTranscript,
  upsertLine,
  shouldFinalize,
  HOLD_THRESHOLD_MS,
  type FinalizeConfig
} from './pushToTalk'
import type { TranscriptLine } from '../../../../shared/types'

const CFG: FinalizeConfig = {
  maxMs: 6000,
  noVoiceGraceMs: 700,
  silenceMs: 450,
  settleMs: 500,
  trailingGraceMs: 1000
}

const line = (text: string, speaker?: string): TranscriptLine => ({ text, speaker })

describe('isHold', () => {
  it('treats a press shorter than the threshold as a tap', () => {
    expect(isHold(1000, 1000 + HOLD_THRESHOLD_MS - 1)).toBe(false)
  })

  it('treats a press at/over the threshold as a hold', () => {
    expect(isHold(1000, 1000 + HOLD_THRESHOLD_MS)).toBe(true)
    expect(isHold(1000, 1000 + HOLD_THRESHOLD_MS + 500)).toBe(true)
  })

  it('honors a custom threshold', () => {
    expect(isHold(0, 200, 250)).toBe(false)
    expect(isHold(0, 300, 250)).toBe(true)
  })
})

describe('assembleTranscript', () => {
  it('returns empty string for no lines and no interim', () => {
    expect(assembleTranscript([], '')).toBe('')
  })

  it('joins finalized lines with a single space, dropping speaker labels', () => {
    expect(assembleTranscript([line('hello', 'You'), line('world', 'Speaker 1')], '')).toBe(
      'hello world'
    )
  })

  it('appends in-progress interim text after the finalized lines', () => {
    expect(assembleTranscript([line('hello')], 'wor')).toBe('hello wor')
  })

  it('trims and drops whitespace-only fragments', () => {
    expect(assembleTranscript([line('  hi  '), line('   ')], '  ')).toBe('hi')
  })

  it('is empty when everything is whitespace', () => {
    expect(assembleTranscript([line('   ')], '   ')).toBe('')
  })
})

describe('upsertLine', () => {
  it('appends lines that have no id (treated as always distinct)', () => {
    const lines: TranscriptLine[] = []
    upsertLine(lines, { text: 'hello' })
    upsertLine(lines, { text: 'world' })
    expect(lines.map((l) => l.text)).toEqual(['hello', 'world'])
  })

  it('appends lines with new ids', () => {
    const lines: TranscriptLine[] = []
    upsertLine(lines, { id: 'a', text: 'hello' })
    upsertLine(lines, { id: 'b', text: 'world' })
    expect(lines.map((l) => l.text)).toEqual(['hello', 'world'])
  })

  it('replaces (does not duplicate) a re-sent segment with the same id', () => {
    const lines: TranscriptLine[] = []
    upsertLine(lines, { id: 'a', text: 'hel' })
    upsertLine(lines, { id: 'a', text: 'hello' }) // refined re-send of segment a
    expect(lines).toHaveLength(1)
    expect(lines[0].text).toBe('hello')
  })

  it('does not duplicate earlier speech when a segment is re-emitted after a pause', () => {
    // Mirrors v4/listen re-sending earlier segments around a pause: assembling the
    // upserted lines must NOT repeat "first part".
    const lines: TranscriptLine[] = []
    upsertLine(lines, { id: 's1', text: 'first part' })
    upsertLine(lines, { id: 's2', text: 'second part' })
    upsertLine(lines, { id: 's1', text: 'first part' }) // re-emit of s1 after the pause
    expect(assembleTranscript(lines, '')).toBe('first part second part')
  })

  it('drops a prior holds segment that the backend echoes into the next hold', () => {
    // Reproduces the observed v4/listen behavior: hold 2 re-receives hold 1's
    // segment (same id) plus the new one. Filtering consumed ids must yield only
    // the new utterance.
    const consumed = new Set<string>()
    // Hold 1: one segment, committed.
    const hold1: TranscriptLine[] = []
    upsertLine(hold1, { id: 'a', text: 'Cystine so yeah' })
    for (const l of hold1) if (l.id) consumed.add(l.id)
    expect(assembleTranscript(hold1, '')).toBe('Cystine so yeah')

    // Hold 2: backend re-sends 'a' (echo) + new 'b'. Echoes are skipped.
    const hold2: TranscriptLine[] = []
    for (const seg of [
      { id: 'a', text: 'Cystine so yeah' },
      { id: 'b', text: 'Do you hear me now' }
    ] as TranscriptLine[]) {
      if (seg.id != null && consumed.has(seg.id)) continue
      upsertLine(hold2, seg)
    }
    expect(assembleTranscript(hold2, '')).toBe('Do you hear me now')
  })
})

describe('shouldFinalize', () => {
  const base = { elapsedMs: 100, everVoiced: true, silentForMs: 0, sinceLastSegmentMs: 100 }

  it('always commits past the hard cap', () => {
    expect(shouldFinalize({ ...base, elapsedMs: CFG.maxMs }, CFG)).toBe(true)
  })

  it('ends quickly when nothing was captured (no voice, no segment)', () => {
    const nothing = { everVoiced: false, silentForMs: 9999, sinceLastSegmentMs: null }
    expect(shouldFinalize({ ...nothing, elapsedMs: CFG.noVoiceGraceMs - 1 }, CFG)).toBe(false)
    expect(shouldFinalize({ ...nothing, elapsedMs: CFG.noVoiceGraceMs }, CFG)).toBe(true)
  })

  it('does not commit while the user is still speaking', () => {
    expect(shouldFinalize({ ...base, silentForMs: CFG.silenceMs - 1, sinceLastSegmentMs: 9999 }, CFG)).toBe(
      false
    )
  })

  it('does not commit until the backend segment has settled', () => {
    // Stopped talking, but a segment just arrived — wait for the trailing final.
    expect(
      shouldFinalize({ ...base, silentForMs: 9999, sinceLastSegmentMs: CFG.settleMs - 1 }, CFG)
    ).toBe(false)
  })

  it('commits once silent and settled, past the trailing grace', () => {
    expect(
      shouldFinalize(
        { ...base, elapsedMs: CFG.trailingGraceMs, silentForMs: CFG.silenceMs, sinceLastSegmentMs: CFG.settleMs },
        CFG
      )
    ).toBe(true)
  })

  it('does NOT commit before the trailing grace, even when silent and settled', () => {
    // A quick release: VAD silence + an old settled segment would otherwise commit
    // in the gap before Omi's ~1.8s-late trailing segment lands, dropping the tail.
    expect(
      shouldFinalize(
        {
          ...base,
          elapsedMs: CFG.trailingGraceMs - 1,
          silentForMs: CFG.silenceMs,
          sinceLastSegmentMs: CFG.settleMs
        },
        CFG
      )
    ).toBe(false)
  })

  it('keeps waiting if voice was detected but no segment has arrived yet', () => {
    expect(
      shouldFinalize(
        { elapsedMs: 1000, everVoiced: true, silentForMs: 9999, sinceLastSegmentMs: null },
        CFG
      )
    ).toBe(false)
  })
})
