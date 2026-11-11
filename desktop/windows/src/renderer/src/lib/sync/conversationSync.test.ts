// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LocalConversation, SyncSegment } from '../../../../shared/types'

// axios + firebase are pulled in transitively; stub the network client so nothing
// leaves the process. We drive behavior through the window.omi fake + claim/post.
const post = vi.fn()
const listRecent = vi.fn().mockResolvedValue({ data: [] })
vi.mock('../apiClient', () => ({
  omiApi: {
    post: (...a: unknown[]) => post(...a),
    get: (...a: unknown[]) => listRecent(...a)
  }
}))
vi.mock('../preferences', () => ({ getPreferences: () => ({ language: 'en' }) }))

import { resyncConversation, syncLocalConversation } from './conversationSync'

const SEGS: SyncSegment[] = [
  { text: 'hi', speaker: 'SPEAKER_0', speaker_id: 0, is_user: true, person_id: null, start: 0, end: 1 }
]

function row(over: Partial<LocalConversation>): LocalConversation {
  return {
    id: 'local-1',
    startedAt: Date.UTC(2026, 6, 10, 12, 0, 0),
    endedAt: Date.UTC(2026, 6, 10, 12, 5, 0),
    transcript: 'You: hi',
    createdAt: Date.UTC(2026, 6, 10, 12, 5, 0),
    syncState: 'pending',
    segments: SEGS,
    ...over
  }
}

let store: Map<string, LocalConversation>
let claim: ReturnType<typeof vi.fn>

beforeEach(() => {
  post.mockReset().mockResolvedValue({ data: { id: 'cloud-new' } })
  listRecent.mockReset().mockResolvedValue({ data: [] })
  store = new Map()
  // Default claim: real CAS semantics against the in-memory store.
  claim = vi.fn(async (id: string, reset?: boolean) => {
    const r = store.get(id)
    if (!r || !['pending', 'failed', 'unconfirmed'].includes(r.syncState ?? 'local_only')) return false
    store.set(id, { ...r, syncState: 'posting', syncAttempts: reset ? 1 : (r.syncAttempts ?? 0) + 1 })
    return true
  })
  vi.stubGlobal('window', {
    omi: {
      getLocalConversation: vi.fn(async (id: string) => store.get(id) ?? null),
      updateLocalConversationSync: vi.fn(async (id: string, patch) => {
        const r = store.get(id)
        if (r) store.set(id, { ...r, ...patch, syncState: patch.syncState })
      }),
      claimConversationForPosting: claim
    }
  })
})

afterEach(() => vi.unstubAllGlobals())

describe('syncLocalConversation — stale-snapshot safety (C1)', () => {
  it('re-reads fresh state: a caller holding a stale pending snapshot bails when the row is already done', async () => {
    // DB truth: already synced. Caller passes a STALE 'pending' snapshot.
    store.set('local-1', row({ syncState: 'done', cloudId: 'cloud-existing' }))
    const out = await syncLocalConversation(row({ syncState: 'pending' }))
    expect(out).toEqual({ status: 'done', cloudId: 'cloud-existing', deduped: false })
    expect(post).not.toHaveBeenCalled() // no duplicate POST
    expect(claim).not.toHaveBeenCalled() // never even claimed
    expect(store.get('local-1')!.syncState).toBe('done') // not clobbered
  })

  it('losing the CAS claim (another driver owns it) yields skipped, no POST', async () => {
    store.set('local-1', row({ syncState: 'pending' }))
    claim.mockResolvedValueOnce(false)
    const out = await syncLocalConversation(row({ syncState: 'pending' }))
    expect(out).toEqual({ status: 'skipped' })
    expect(post).not.toHaveBeenCalled()
  })

  it('happy path: fresh pending → claim wins → POST → done', async () => {
    store.set('local-1', row({ syncState: 'pending' }))
    const out = await syncLocalConversation(row({ syncState: 'pending' }))
    expect(out).toMatchObject({ status: 'done', cloudId: 'cloud-new' })
    expect(claim).toHaveBeenCalledWith('local-1')
    expect(post).toHaveBeenCalledOnce()
  })

  it('a crash-orphaned posting row is recovered to unconfirmed (dedupe runs before any re-post)', async () => {
    store.set('local-1', row({ syncState: 'posting' }))
    listRecent.mockResolvedValueOnce({
      data: [{ id: 'cloud-twin', started_at: '2026-07-10T12:00:00.000Z', finished_at: '2026-07-10T12:05:00.000Z' }]
    })
    const out = await syncLocalConversation(row({ syncState: 'posting' }))
    expect(out).toMatchObject({ status: 'done', cloudId: 'cloud-twin', deduped: true })
    expect(post).not.toHaveBeenCalled() // adopted the twin, did not duplicate
  })
})

describe('resyncConversation — manual recovery of a wedged row (M2)', () => {
  it('re-drives a failed row, resetting the attempt cap via claim(reset=true)', async () => {
    store.set('local-1', row({ syncState: 'failed', syncAttempts: 10 }))
    const out = await resyncConversation('local-1')
    expect(out).toMatchObject({ status: 'done', cloudId: 'cloud-new' })
    expect(claim).toHaveBeenCalledWith('local-1', true) // attempts reset
    expect(post).toHaveBeenCalledOnce()
  })

  it('refuses a segmentless or missing row', async () => {
    store.set('local-1', row({ syncState: 'failed', segments: [] }))
    expect(await resyncConversation('local-1')).toBeNull()
    expect(await resyncConversation('nope')).toBeNull()
    expect(post).not.toHaveBeenCalled()
  })
})
