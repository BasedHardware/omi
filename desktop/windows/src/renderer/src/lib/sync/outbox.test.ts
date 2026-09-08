import { describe, expect, it, vi } from 'vitest'
import {
  buildFromSegmentsRequest,
  canTransition,
  findCloudMatch,
  queueForSync,
  syncConversation,
  type SyncDeps,
  type SyncableConversation
} from './outbox'
import type { ConversationSyncPatch, SyncSegment } from '../../../../shared/types'

const SEGMENTS: SyncSegment[] = [
  { text: 'hello', speaker: 'SPEAKER_0', speaker_id: 0, is_user: true, person_id: null, start: 0, end: 1 },
  { text: 'world', speaker: 'SPEAKER_1', speaker_id: 1, is_user: false, person_id: null, start: 2, end: 3 }
]

function conv(over: Partial<SyncableConversation> = {}): SyncableConversation {
  return {
    id: 'local-abc',
    startedAt: Date.UTC(2026, 6, 10, 12, 0, 0),
    endedAt: Date.UTC(2026, 6, 10, 12, 5, 0),
    segments: SEGMENTS,
    syncState: 'pending',
    ...over
  }
}

type PersistCall = { id: string; patch: ConversationSyncPatch }

function makeDeps(over: Partial<SyncDeps> = {}): SyncDeps & { persisted: PersistCall[] } {
  const persisted: PersistCall[] = []
  return {
    persisted,
    post: vi.fn().mockResolvedValue({ id: 'cloud-1' }),
    listRecent: vi.fn().mockResolvedValue([]),
    persist: vi.fn(async (id: string, patch: ConversationSyncPatch) => {
      persisted.push({ id, patch })
    }),
    claim: vi.fn().mockResolvedValue(true),
    ...over
  }
}

describe('canTransition (state machine)', () => {
  it('allows exactly the documented edges', () => {
    expect(canTransition('local_only', 'pending')).toBe(true)
    expect(canTransition('pending', 'posting')).toBe(true)
    expect(canTransition('posting', 'done')).toBe(true)
    expect(canTransition('posting', 'failed')).toBe(true)
    expect(canTransition('posting', 'unconfirmed')).toBe(true)
    expect(canTransition('failed', 'posting')).toBe(true)
    expect(canTransition('unconfirmed', 'posting')).toBe(true)
    expect(canTransition('unconfirmed', 'done')).toBe(true)
    // The dangerous edges stay closed:
    expect(canTransition('pending', 'done')).toBe(false) // no done without a POST
    expect(canTransition('done', 'posting')).toBe(false) // done is terminal
    expect(canTransition('local_only', 'posting')).toBe(false) // must queue first
    expect(canTransition('unconfirmed', 'failed')).toBe(false)
  })
})

describe('queueForSync', () => {
  const base = { id: 'l1', startedAt: 0, endedAt: 60_000, transcript: 'You: hi', createdAt: 1 }

  it('queues rows with segments as pending; segmentless rows stay local_only', () => {
    expect(queueForSync(base, SEGMENTS)).toMatchObject({ syncState: 'pending', segments: SEGMENTS })
    expect(queueForSync(base, [])).toMatchObject({ syncState: 'local_only', segments: [] })
  })
})

describe('buildFromSegmentsRequest', () => {
  it('carries real wall-clock times, desktop provenance, and the future idempotency key', () => {
    const req = buildFromSegmentsRequest(conv(), 'en')
    expect(req.transcript_segments).toBe(SEGMENTS)
    expect(req.started_at).toBe('2026-07-10T12:00:00.000Z')
    expect(req.finished_at).toBe('2026-07-10T12:05:00.000Z')
    expect(req.source).toBe('desktop') // the only provenance field that round-trips on prod
    expect(req.client_platform).toBe('windows')
    expect(req.client_session_id).toBe('local-abc') // ignored on prod today; idempotency later
    expect(req.language).toBe('en')
  })
})

describe('findCloudMatch', () => {
  const local = { startedAt: Date.UTC(2026, 6, 10, 12, 0, 0), endedAt: Date.UTC(2026, 6, 10, 12, 5, 0), segmentCount: 2 }

  it('matches on round-tripped started_at/finished_at within tolerance', () => {
    expect(
      findCloudMatch(local, [
        { id: 'c1', started_at: '2026-07-10T12:00:00.500Z', finished_at: '2026-07-10T12:05:00.000Z' }
      ])
    ).toBe('c1')
  })

  it('rejects conversations outside the window (no false adoption)', () => {
    expect(
      findCloudMatch(local, [
        { id: 'far', started_at: '2026-07-10T12:00:10.000Z', finished_at: '2026-07-10T12:05:00.000Z' },
        { id: 'wrong-end', started_at: '2026-07-10T12:00:00.000Z', finished_at: '2026-07-10T12:09:00.000Z' },
        { id: 'no-start', started_at: null }
      ])
    ).toBeNull()
  })

  it('prefers an exact segment-count match, then the closest started_at', () => {
    expect(
      findCloudMatch(local, [
        { id: 'close-wrong-count', started_at: '2026-07-10T12:00:00.100Z', transcript_segments: [1, 2, 3] },
        { id: 'right-count', started_at: '2026-07-10T12:00:01.000Z', transcript_segments: [1, 2] }
      ])
    ).toBe('right-count')
  })
})

describe('syncConversation', () => {
  it('happy path: pending → posting → done, persisting each transition in order', async () => {
    const deps = makeDeps()
    const out = await syncConversation(conv(), deps)
    expect(out).toEqual({ status: 'done', cloudId: 'cloud-1', deduped: false })
    // The posting flip is the CAS claim (not a persist); persist only records done.
    expect(deps.claim).toHaveBeenCalledWith('local-abc')
    expect(deps.persisted.map((p) => p.patch.syncState)).toEqual(['done'])
    expect(deps.persisted.at(-1)!.patch).toMatchObject({ cloudId: 'cloud-1', syncError: null })
  })

  it('lost CAS claim → skipped, no POST, no state churn (the duplicate-prevention property)', async () => {
    const deps = makeDeps({ claim: vi.fn().mockResolvedValue(false) })
    const out = await syncConversation(conv(), deps)
    expect(out).toEqual({ status: 'skipped' })
    expect(deps.post).not.toHaveBeenCalled()
    expect(deps.persisted).toHaveLength(0)
  })

  it('a definite HTTP failure lands in failed (safe to re-post later)', async () => {
    const deps = makeDeps({
      post: vi.fn().mockRejectedValue({ ambiguous: false, message: 'HTTP 422 bad segment' })
    })
    const out = await syncConversation(conv(), deps)
    expect(out).toEqual({ status: 'failed', error: 'HTTP 422 bad segment' })
    expect(deps.persisted.at(-1)!.patch).toMatchObject({ syncState: 'failed', syncError: 'HTTP 422 bad segment' })
  })

  it('an ambiguous failure (timeout after send) lands in unconfirmed — never failed', async () => {
    const deps = makeDeps({ post: vi.fn().mockRejectedValue({ ambiguous: true, message: 'timeout' }) })
    const out = await syncConversation(conv(), deps)
    expect(out.status).toBe('unconfirmed')
    expect(deps.persisted.at(-1)!.patch.syncState).toBe('unconfirmed')
  })

  it('an UNCLASSIFIED rejection defaults to unconfirmed (never blind-repost on a maybe)', async () => {
    const deps = makeDeps({ post: vi.fn().mockRejectedValue(new Error('weird')) })
    const out = await syncConversation(conv(), deps)
    expect(out.status).toBe('unconfirmed')
  })

  it('unconfirmed retry: dedupe check finds the cloud twin and ADOPTS it without re-posting', async () => {
    const deps = makeDeps({
      listRecent: vi.fn().mockResolvedValue([
        { id: 'cloud-twin', started_at: '2026-07-10T12:00:00.000Z', finished_at: '2026-07-10T12:05:00.000Z' }
      ])
    })
    const out = await syncConversation(conv({ syncState: 'unconfirmed' }), deps)
    expect(out).toEqual({ status: 'done', cloudId: 'cloud-twin', deduped: true })
    expect(deps.post).not.toHaveBeenCalled() // THE duplicate-prevention property
    expect(deps.persisted.at(-1)!.patch).toMatchObject({ syncState: 'done', cloudId: 'cloud-twin' })
  })

  it('unconfirmed retry: no cloud twin → the earlier POST never landed → re-posts once', async () => {
    const deps = makeDeps({ listRecent: vi.fn().mockResolvedValue([{ id: 'other', started_at: '2026-07-10T09:00:00.000Z' }]) })
    const out = await syncConversation(conv({ syncState: 'unconfirmed' }), deps)
    expect(deps.listRecent).toHaveBeenCalledOnce()
    expect(deps.post).toHaveBeenCalledOnce()
    expect(out.status).toBe('done')
  })

  it('unconfirmed retry: dedupe check itself failing stays unconfirmed and does NOT post', async () => {
    const deps = makeDeps({ listRecent: vi.fn().mockRejectedValue(new Error('offline')) })
    const out = await syncConversation(conv({ syncState: 'unconfirmed' }), deps)
    expect(out.status).toBe('unconfirmed')
    expect(deps.post).not.toHaveBeenCalled()
    expect(deps.persisted).toHaveLength(0) // no state churn — retry later re-runs the check
  })

  it('local_only (backfill) passes through pending before claiming', async () => {
    const deps = makeDeps()
    const out = await syncConversation(conv({ syncState: 'local_only' }), deps)
    expect(out.status).toBe('done')
    // pending persisted, then the CAS claim flips to posting, then done persisted.
    expect(deps.persisted.map((p) => p.patch.syncState)).toEqual(['pending', 'done'])
    expect(deps.claim).toHaveBeenCalledOnce()
  })

  it('done input is a no-op; a row already posting throws (caller bug)', async () => {
    const deps = makeDeps()
    const out = await syncConversation(conv({ syncState: 'done', cloudId: 'c9' }), deps)
    expect(out).toEqual({ status: 'done', cloudId: 'c9', deduped: false })
    expect(deps.post).not.toHaveBeenCalled()
    await expect(syncConversation(conv({ syncState: 'posting' }), deps)).rejects.toThrow(/already posting/)
  })

  it('empty segments fail fast without touching the network', async () => {
    const deps = makeDeps()
    const out = await syncConversation(conv({ segments: [] }), deps)
    expect(out.status).toBe('failed')
    expect(deps.post).not.toHaveBeenCalled()
  })
})
