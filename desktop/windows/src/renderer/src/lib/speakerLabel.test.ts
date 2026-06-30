import { describe, it, expect } from 'vitest'
import { speakerLabel, countDistinctSpeakers, makeSpeakerLabeler } from './speakerLabel'

describe('speakerLabel (single-speaker context)', () => {
  it('labels the wearer as "You"', () => {
    expect(speakerLabel({ is_user: true, speaker: 'SPEAKER_00', text: '' })).toBe('You')
  })

  it('turns a raw diarization tag into a readable "Speaker N"', () => {
    expect(speakerLabel({ speaker: 'SPEAKER_00', text: '' })).toBe('Speaker 0')
    expect(speakerLabel({ speaker: 'SPEAKER_2', text: '' })).toBe('Speaker 2')
    expect(speakerLabel({ speaker: 'speaker_3', text: '' })).toBe('Speaker 3')
  })

  it('uses speaker_id when there is no speaker string', () => {
    expect(speakerLabel({ speaker_id: 1, text: '' })).toBe('Speaker 1')
  })

  it('keeps a real assigned name as-is', () => {
    expect(speakerLabel({ speaker: 'Alice', text: '' })).toBe('Alice')
  })

  it('prefers a matched person_name', () => {
    expect(speakerLabel({ speaker_id: 2, person_name: 'Bob', text: '' })).toBe('Bob')
  })

  it('returns undefined when there is no speaker information', () => {
    expect(speakerLabel({ text: '' })).toBeUndefined()
  })
})

describe('speakerLabel (multi-speaker / explicit wearer)', () => {
  it('labels the wearer "You" regardless of id', () => {
    expect(speakerLabel({ speaker_id: 3, text: '' }, true, true)).toBe('You')
  })

  it('differentiates non-wearers by speaker_id', () => {
    expect(speakerLabel({ speaker_id: 0, text: '' }, true, false)).toBe('Speaker 0')
    expect(speakerLabel({ speaker_id: 1, text: '' }, true, false)).toBe('Speaker 1')
  })

  it('names a matched person over a number', () => {
    expect(speakerLabel({ speaker_id: 1, person_name: 'Carol', text: '' }, true, false)).toBe('Carol')
  })
})

describe('countDistinctSpeakers', () => {
  it('counts distinct diarization ids', () => {
    expect(
      countDistinctSpeakers([{ speaker_id: 0, text: '' }, { speaker_id: 1, text: '' }, { speaker_id: 0, text: '' }])
    ).toBe(2)
  })

  it('keeps mic and system speakers separate (same id, different source)', () => {
    expect(
      countDistinctSpeakers([
        { speaker_id: 0, source: 'mic', text: '' },
        { speaker_id: 0, source: 'system', text: '' }
      ])
    ).toBe(2)
  })
})

describe('makeSpeakerLabeler', () => {
  it('local recording: mic = You, system speakers numbered', () => {
    const segs = [
      { source: 'mic', is_user: true, speaker_id: 0, text: '' },
      { source: 'system', is_user: true, speaker_id: 0, text: '' },
      { source: 'system', is_user: true, speaker_id: 1, text: '' }
    ]
    const label = makeSpeakerLabeler(segs)
    expect(label(segs[0])).toBe('You')
    expect(label(segs[1])).toBe('Speaker 0')
    expect(label(segs[2])).toBe('Speaker 1')
  })

  it('server conversation with per-speaker is_user: the wearer is You', () => {
    // identification ran ⇒ is_user varies ⇒ trust it
    const segs = [
      { is_user: true, speaker_id: 0, text: '' },
      { is_user: false, speaker_id: 1, text: '' }
    ]
    const label = makeSpeakerLabeler(segs)
    expect(label(segs[0])).toBe('You')
    expect(label(segs[1])).toBe('Speaker 1')
  })

  it('single mic channel (uniform is_user): the primary voice is You, others numbered', () => {
    // The backend stamps every segment is_user=true on one mic channel, so the
    // wearer = the lowest diarization id (the user, who opens the conversation).
    const segs = [
      { is_user: true, speaker_id: 0, text: '' },
      { is_user: true, speaker_id: 1, text: '' },
      { is_user: true, speaker_id: 0, text: '' }
    ]
    const label = makeSpeakerLabeler(segs)
    expect(label(segs[0])).toBe('You')
    expect(label(segs[1])).toBe('Speaker 1')
    expect(label(segs[2])).toBe('You')
  })

  it('resolves the primary voice as You even when is_user is absent on stored segments', () => {
    // The common case: the server returns SPEAKER_00/SPEAKER_01 with no usable
    // is_user. It's the user's own recording, so the primary voice is them.
    const segs = [
      { speaker: 'SPEAKER_00', text: '' },
      { speaker: 'SPEAKER_01', text: '' },
      { speaker: 'SPEAKER_00', text: '' }
    ]
    const label = makeSpeakerLabeler(segs)
    expect(label(segs[0])).toBe('You')
    expect(label(segs[1])).toBe('Speaker 1')
  })

  it('single speaker is still You', () => {
    const segs = [{ is_user: true, speaker_id: 0, text: '' }]
    expect(makeSpeakerLabeler(segs)(segs[0])).toBe('You')
  })
})
