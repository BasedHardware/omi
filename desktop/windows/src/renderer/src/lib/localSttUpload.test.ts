import { describe, expect, it, vi } from 'vitest'
import { buildUploadSegments } from './localSttUpload'

vi.mock('./apiClient', () => ({
  omiApi: { post: vi.fn() }
}))

describe('local STT upload mapping', () => {
  it('merges adjacent same-speaker lines and preserves backend timing fields', () => {
    const segments = buildUploadSegments([
      {
        id: 'a',
        speaker: 'You',
        text: 'hello',
        isUser: true,
        speakerId: 0,
        start: 0,
        end: 1
      },
      {
        id: 'b',
        speaker: 'You',
        text: 'world',
        isUser: true,
        speakerId: 0,
        start: 1.4,
        end: 2
      },
      {
        id: 'c',
        speaker: 'SPEAKER_1',
        text: 'reply',
        isUser: false,
        start: 2.2,
        end: 3
      }
    ])

    expect(segments).toEqual([
      {
        text: 'hello world',
        speaker: 'SPEAKER_0',
        speaker_id: 0,
        is_user: true,
        person_id: undefined,
        start: 0,
        end: 2
      },
      {
        text: 'reply',
        speaker: 'SPEAKER_1',
        speaker_id: 1,
        is_user: false,
        person_id: undefined,
        start: 2.2,
        end: 3
      }
    ])
  })

  it('fills missing timing with monotonic fallback durations', () => {
    const segments = buildUploadSegments([{ text: 'one two three' }, { text: 'next' }])

    expect(segments).toHaveLength(1)
    expect(segments[0].start).toBe(0)
    expect(segments[0].end).toBeGreaterThan(1)
    expect(segments[0].text).toBe('one two three next')
  })
})
