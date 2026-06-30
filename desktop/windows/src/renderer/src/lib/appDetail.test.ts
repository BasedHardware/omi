import { it, expect, describe } from 'vitest'
import {
  capabilityLabel,
  triggerLabel,
  formatInstalls,
  setupUrl,
  reviewerName,
  reviewsWithText,
  filledStars,
  thumbnailUrl,
  previewUrls
} from './appDetail'

describe('capabilityLabel', () => {
  it('maps known capabilities to store wording', () => {
    expect(capabilityLabel('external_integration')).toBe('External Integration')
    expect(capabilityLabel('proactive_notification')).toBe('Proactive Notification')
    expect(capabilityLabel('chat')).toBe('Chat')
  })
  it('title-cases unknown tags as a fallback', () => {
    expect(capabilityLabel('some_new_thing')).toBe('Some New Thing')
  })
})

describe('triggerLabel', () => {
  it('renames the legacy memory_creation trigger to Conversation Creation', () => {
    expect(triggerLabel('memory_creation')).toBe('Conversation Creation')
    expect(triggerLabel('transcript_processed')).toBe('Transcript Processed')
    expect(triggerLabel('audio_bytes')).toBe('Realtime Audio Bytes')
  })
  it('returns null for missing trigger', () => {
    expect(triggerLabel(null)).toBeNull()
    expect(triggerLabel(undefined)).toBeNull()
  })
})

describe('formatInstalls', () => {
  it('formats large counts compactly, lowercase k', () => {
    expect(formatInstalls(44900)).toBe('44.9k')
    expect(formatInstalls(1500)).toBe('1.5k')
  })
  it('leaves small counts plain and omits nullish/zero', () => {
    expect(formatInstalls(999)).toBe('999')
    expect(formatInstalls(0)).toBe('')
    expect(formatInstalls(null)).toBe('')
    expect(formatInstalls(undefined)).toBe('')
  })
})

describe('setupUrl', () => {
  it('prefers setup_completed_url, then app_home_url, then first auth step', () => {
    expect(setupUrl({ setup_completed_url: 'https://a', app_home_url: 'https://b' })).toBe('https://a')
    expect(setupUrl({ app_home_url: 'https://b' })).toBe('https://b')
    expect(setupUrl({ auth_steps: [{ name: 's', url: 'https://c' }] })).toBe('https://c')
  })
  it('returns null when nothing is configured', () => {
    expect(setupUrl(null)).toBeNull()
    expect(setupUrl({})).toBeNull()
    expect(setupUrl({ auth_steps: [] })).toBeNull()
  })
})

describe('reviewerName', () => {
  it('uses the username, falling back to Anonymous', () => {
    expect(reviewerName({ username: 'jane' })).toBe('jane')
    expect(reviewerName({ username: '  ' })).toBe('Anonymous')
    expect(reviewerName({})).toBe('Anonymous')
  })
})

describe('reviewsWithText', () => {
  it('keeps only reviews with non-empty text (rating-only entries are dropped)', () => {
    const out = reviewsWithText([
      { score: 5, review: 'nice one' },
      { score: 1, review: '' },
      { score: 4 },
      { score: 3, review: '  ' }
    ])
    expect(out).toHaveLength(1)
    expect(out[0].review).toBe('nice one')
  })
  it('tolerates non-array input', () => {
    expect(reviewsWithText(undefined)).toEqual([])
  })
})

describe('previewUrls', () => {
  it('builds preview URLs from thumbnail ids (fast list) — load with the page', () => {
    expect(previewUrls({ thumbnails: ['abc', 'def'] })).toEqual([
      thumbnailUrl('abc'),
      thumbnailUrl('def')
    ])
    expect(thumbnailUrl('abc')).toBe('https://storage.googleapis.com/app_thumbnails/abc.jpg')
  })
  it('prefers authoritative thumbnail_urls when present', () => {
    expect(previewUrls({ thumbnail_urls: ['https://x/y.jpg'], thumbnails: ['abc'] })).toEqual([
      'https://x/y.jpg'
    ])
  })
  it('passes through ids that are already absolute urls, and handles empty', () => {
    expect(previewUrls({ thumbnails: ['https://cdn/z.jpg'] })).toEqual(['https://cdn/z.jpg'])
    expect(previewUrls({})).toEqual([])
  })
})

describe('filledStars', () => {
  it('rounds the score and clamps to 0..5', () => {
    expect(filledStars(3.3)).toBe(3)
    expect(filledStars(4.6)).toBe(5)
    expect(filledStars(0)).toBe(0)
    expect(filledStars(9)).toBe(5)
    expect(filledStars(null)).toBe(0)
  })
})
