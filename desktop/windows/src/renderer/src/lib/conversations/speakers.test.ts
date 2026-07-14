import { describe, it, expect } from 'vitest'
import type { TranscriptSegment } from '../omiApi.generated'
import {
  AVATAR_NAMED,
  AVATAR_NAMED_SOFT,
  AVATAR_UNNAMED,
  SPEAKER_COLORS,
  USER_BUBBLE,
  avatarFill,
  avatarInitial,
  bubbleColor,
  collectSpeakerSegments,
  parseSpeakerId,
  personNameFor,
  segmentIdsToAssign,
  speakerIdOf,
  speakerLabel
} from './speakers'

function seg(over: Partial<TranscriptSegment> = {}): TranscriptSegment {
  return { text: 'hi', start: 0, end: 1, is_user: false, ...over }
}

describe('parseSpeakerId', () => {
  it('pulls the index out of a SPEAKER_NN string', () => {
    expect(parseSpeakerId('SPEAKER_04')).toBe(4)
    expect(parseSpeakerId('SPEAKER_0')).toBe(0)
    expect(parseSpeakerId('SPEAKER_11')).toBe(11)
  })

  it('defaults to 0 when unparseable', () => {
    expect(parseSpeakerId(undefined)).toBe(0)
    expect(parseSpeakerId(null)).toBe(0)
    expect(parseSpeakerId('')).toBe(0)
    expect(parseSpeakerId('SPEAKER_XX')).toBe(0)
    expect(parseSpeakerId('nonsense')).toBe(0)
  })

  it('falls back to the structured speaker_id only when there is no string', () => {
    expect(speakerIdOf(seg({ speaker: 'SPEAKER_02', speaker_id: 9 }))).toBe(2) // string wins
    expect(speakerIdOf(seg({ speaker: null, speaker_id: 9 }))).toBe(9)
    expect(speakerIdOf(seg({}))).toBe(0)
  })
})

describe('bubbleColor', () => {
  it('cycles the 6-tone palette by speakerId % 6', () => {
    expect(bubbleColor(0, false)).toBe('#2D3748')
    expect(bubbleColor(4, false)).toBe('#3D2E4A')
    expect(bubbleColor(5, false)).toBe('#4A3A2D')
    // wraps
    expect(bubbleColor(6, false)).toBe(SPEAKER_COLORS[0])
    expect(bubbleColor(13, false)).toBe(SPEAKER_COLORS[1])
  })

  it('always gives the user the userBubble fill, whatever their speakerId', () => {
    expect(bubbleColor(0, true)).toBe(USER_BUBBLE)
    expect(bubbleColor(3, true)).toBe(USER_BUBBLE)
    expect(USER_BUBBLE).toBe('#43389F')
  })
})

describe('avatarInitial / avatarFill', () => {
  it('shows Y for the user', () => {
    expect(avatarInitial(2, true)).toBe('Y')
    expect(avatarFill(true)).toBe(AVATAR_NAMED)
  })

  it("shows a named person's first letter, uppercased", () => {
    expect(avatarInitial(1, false, 'nikita')).toBe('N')
    expect(avatarFill(false, 'nikita')).toBe(AVATAR_NAMED_SOFT)
  })

  it('shows the raw speaker digit when nobody has named them', () => {
    expect(avatarInitial(3, false)).toBe('3')
    expect(avatarInitial(3, false, '   ')).toBe('3') // whitespace is not a name
    expect(avatarFill(false)).toBe(AVATAR_UNNAMED)
    expect(AVATAR_UNNAMED).toBe('#35343B')
  })
})

describe('speakerLabel / personNameFor', () => {
  const people = [
    { id: 'p1', name: 'Nikita' },
    { id: 'p2', name: 'Chris' }
  ]

  it('resolves a segment person_id against the account-wide roster', () => {
    expect(personNameFor(seg({ person_id: 'p2' }), people)).toBe('Chris')
    expect(personNameFor(seg({ person_id: 'gone' }), people)).toBeNull()
    expect(personNameFor(seg({}), people)).toBeNull()
  })

  it('labels user / named / unnamed', () => {
    expect(speakerLabel(0, true)).toBe('You')
    expect(speakerLabel(1, false, 'Chris')).toBe('Chris')
    expect(speakerLabel(1, false)).toBe('Speaker 1')
  })
})

describe('collectSpeakerSegments — "also tag N other segments"', () => {
  const segments = [
    seg({ id: 's0', speaker: 'SPEAKER_00' }),
    seg({ id: 's1', speaker: 'SPEAKER_01' }),
    seg({ id: 's2', speaker: 'SPEAKER_00' }),
    seg({ id: 's3', speaker: 'SPEAKER_00', is_user: true }), // user, not this speaker
    seg({ id: 's4', speaker: 'SPEAKER_01' })
  ]

  it('gathers every segment from that speaker in this conversation', () => {
    const r = collectSpeakerSegments(segments, 1)
    expect(r.ids).toEqual(['s1', 's4'])
    expect(r.total).toBe(2)
    expect(r.unsyncedCount).toBe(0)
  })

  it("never sweeps in the user's own segments", () => {
    const r = collectSpeakerSegments(segments, 0)
    expect(r.ids).toEqual(['s0', 's2']) // s3 is is_user
  })

  // The Mac bug this PR fixes: Mac substitutes a synthetic "#index:N" id for
  // segments with no backend id. The server looks up by REAL id, so those entries
  // match nothing and the PATCH silently no-ops — the user names a speaker and
  // nothing happens. We must never emit such an id.
  it('drops unsynced segments instead of inventing "#index:N" ids', () => {
    const withUnsynced = [
      seg({ id: 's0', speaker: 'SPEAKER_00' }),
      seg({ id: undefined, speaker: 'SPEAKER_00' }),
      seg({ id: '', speaker: 'SPEAKER_00' })
    ]
    const r = collectSpeakerSegments(withUnsynced, 0)

    expect(r.ids).toEqual(['s0'])
    expect(r.unsyncedCount).toBe(2)
    expect(r.total).toBe(3)
    // the actual regression guard — no fabricated ids of any shape
    for (const id of r.ids) {
      expect(id).not.toMatch(/^#index:/)
      expect(id).toBeTruthy()
    }
  })

  it('yields no ids at all when the whole speaker is unsynced', () => {
    const r = collectSpeakerSegments([seg({ speaker: 'SPEAKER_02' })], 2)
    expect(r.ids).toEqual([])
    expect(r.unsyncedCount).toBe(1)
  })
})

describe('segmentIdsToAssign', () => {
  const segments = [
    seg({ id: 's0', speaker: 'SPEAKER_00' }),
    seg({ id: 's1', speaker: 'SPEAKER_00' }),
    seg({ id: 's2', speaker: 'SPEAKER_01' })
  ]

  it('applies to every segment from the speaker when the toggle is on (the default)', () => {
    expect(segmentIdsToAssign(segments, segments[0], true)).toEqual(['s0', 's1'])
  })

  it('applies to just the tapped segment when the toggle is off', () => {
    expect(segmentIdsToAssign(segments, segments[0], false)).toEqual(['s0'])
  })

  it('returns nothing for an unsynced tapped segment rather than a fake id', () => {
    const unsynced = seg({ speaker: 'SPEAKER_03' })
    expect(segmentIdsToAssign([unsynced], unsynced, false)).toEqual([])
    expect(segmentIdsToAssign([unsynced], unsynced, true)).toEqual([])
  })
})
