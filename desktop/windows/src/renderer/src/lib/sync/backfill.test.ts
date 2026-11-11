import { describe, expect, it, vi } from 'vitest'

// backfill → conversationSync → apiClient → firebase evaluates `getAuth()` at import,
// which throws `auth/invalid-api-key` when VITE_FIREBASE_* is unset (CI has no .env).
// These are pure-data tests that never touch auth, so stub the module — same pattern as
// omiListenClient.test.ts / ptt/transport.test.ts.
vi.mock('../firebase', () => ({ auth: { currentUser: null } }))

import { BACKFILL_HOURLY_CAP, backfillCandidates, planBackfill, transcriptToSegments } from './backfill'
import type { LocalConversation } from '../../../../shared/types'

function local(over: Partial<LocalConversation>): LocalConversation {
  return {
    id: 'l1',
    startedAt: 0,
    endedAt: 60_000,
    transcript: 'You: hello',
    createdAt: 1,
    ...over
  }
}

describe('backfillCandidates', () => {
  it('selects only legacy local_only recordings with transcript text', () => {
    const rows = [
      local({ id: 'legacy' }), // syncState absent = local_only
      local({ id: 'explicit', syncState: 'local_only' }),
      local({ id: 'chat', kind: 'chat' }),
      local({ id: 'queued', syncState: 'pending' }),
      local({ id: 'synced', syncState: 'done' }),
      local({ id: 'failed', syncState: 'failed' }), // retry pass owns these
      local({ id: 'empty', transcript: '   ' })
    ]
    expect(backfillCandidates(rows).map((c) => c.id)).toEqual(['legacy', 'explicit'])
  })
})

describe('planBackfill (≤25/hour, resumable)', () => {
  const now = 10 * 3_600_000
  const ids = Array.from({ length: 40 }, (_, i) => `c${i}`)

  it('posts up to the hourly cap when history is empty', () => {
    const plan = planBackfill(ids, [], now)
    expect(plan.postNow).toHaveLength(BACKFILL_HOURLY_CAP)
    expect(plan.waitMs).toBe(3_600_000) // capped with no history slot to expire
  })

  it('subtracts posts already made within the sliding hour', () => {
    const history = Array.from({ length: 20 }, (_, i) => now - 30 * 60_000 + i)
    const plan = planBackfill(ids, history, now)
    expect(plan.postNow).toHaveLength(5)
    expect(plan.waitMs).toBeCloseTo(30 * 60_000, -3) // oldest in-window slot frees in ~30min
  })

  it('ignores posts older than an hour and returns null wait when everything fits', () => {
    const plan = planBackfill(['a', 'b'], [now - 2 * 3_600_000], now)
    expect(plan.postNow).toEqual(['a', 'b'])
    expect(plan.waitMs).toBeNull()
  })

  it('fully capped: posts nothing, reports the wait', () => {
    const history = Array.from({ length: 25 }, (_, i) => now - 10 * 60_000 + i)
    const plan = planBackfill(ids, history, now)
    expect(plan.postNow).toHaveLength(0)
    expect(plan.waitMs).toBeGreaterThan(0)
  })
})

describe('transcriptToSegments', () => {
  it('parses lane headers + speaker prefixes into the from-segments shape', () => {
    const segs = transcriptToSegments(
      'Microphone:\nYou: hello there\nSpeaker 1: hi\n\nSystem audio:\nwelcome to the meeting',
      100
    )
    expect(segs).toHaveLength(3)
    expect(segs[0]).toMatchObject({ text: 'hello there', is_user: true, speaker_id: 0, speaker: 'You' })
    expect(segs[1]).toMatchObject({ text: 'hi', is_user: false, speaker: 'Speaker 1' })
    expect(segs[2]).toMatchObject({ text: 'welcome to the meeting', is_user: false })
    expect(segs[1].speaker_id).not.toBe(segs[2].speaker_id) // labeled vs system-lane bucket
  })

  it('spreads times proportionally across the real duration, monotonic and within bounds', () => {
    const segs = transcriptToSegments('You: aaaa\nYou: bb', 60)
    expect(segs[0].start).toBe(0)
    expect(segs[0].end).toBeCloseTo(40, 1) // 4 of 6 chars
    expect(segs[1].start).toBeCloseTo(40, 1)
    expect(segs[1].end).toBeCloseTo(60, 1)
  })

  it('handles unprefixed mic lines as the user and empty transcripts as no segments', () => {
    const segs = transcriptToSegments('just raw text', 10)
    expect(segs).toHaveLength(1)
    expect(segs[0].is_user).toBe(true)
    expect(transcriptToSegments('   \n  ', 10)).toEqual([])
  })
})
