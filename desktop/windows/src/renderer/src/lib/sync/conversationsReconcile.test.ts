import { describe, expect, it, vi } from 'vitest'
import { findSyncedMatches, hideSyncedLocals, reconcileSyncedLocals } from './conversationsReconcile'
import type { LocalConversation, SyncSegment } from '../../../../shared/types'

const SEGS: SyncSegment[] = [
  { text: 'hi', speaker: 'SPEAKER_0', speaker_id: 0, is_user: true, person_id: null, start: 0, end: 1 }
]

function local(over: Partial<LocalConversation>): LocalConversation {
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

describe('findSyncedMatches', () => {
  const cloudTwin = {
    id: 'cloud-9',
    started_at: '2026-07-10T12:00:00.000Z',
    finished_at: '2026-07-10T12:05:00.000Z'
  }

  it('matches an awaiting-sync local row to its cloud twin', () => {
    expect(findSyncedMatches([local({ syncState: 'unconfirmed' })], [cloudTwin])).toEqual([
      { id: 'local-1', cloudId: 'cloud-9' }
    ])
  })

  it('ignores rows that never entered the pipeline, finished rows, and segmentless rows', () => {
    expect(findSyncedMatches([local({ syncState: 'local_only' })], [cloudTwin])).toEqual([])
    expect(findSyncedMatches([local({ syncState: 'done', cloudId: 'cloud-9' })], [cloudTwin])).toEqual([])
    expect(findSyncedMatches([local({ segments: [] })], [cloudTwin])).toEqual([])
  })

  it('does not adopt an unrelated cloud conversation (window mismatch)', () => {
    expect(
      findSyncedMatches([local({})], [{ id: 'other', started_at: '2026-07-10T11:00:00.000Z' }])
    ).toEqual([])
  })
})

describe('reconcileSyncedLocals', () => {
  const cloudTwin = {
    id: 'cloud-9',
    started_at: '2026-07-10T12:00:00.000Z',
    finished_at: '2026-07-10T12:05:00.000Z'
  }

  it('adopts the twin: persists the done transition and reflects it in the returned rows', () => {
    const persist = vi.fn().mockResolvedValue(undefined)
    const out = reconcileSyncedLocals([local({ syncState: 'unconfirmed' })], [cloudTwin], persist)
    expect(persist).toHaveBeenCalledWith('local-1', { syncState: 'done', cloudId: 'cloud-9', syncError: null })
    expect(out[0]).toMatchObject({ syncState: 'done', cloudId: 'cloud-9' })
  })

  it('no matches → returns the input untouched, persists nothing', () => {
    const persist = vi.fn()
    const locals = [local({ syncState: 'local_only' })]
    expect(reconcileSyncedLocals(locals, [cloudTwin], persist)).toBe(locals)
    expect(persist).not.toHaveBeenCalled()
  })
})

describe('hideSyncedLocals', () => {
  it('hides a done row whose cloud twin is in the fetched list', () => {
    const rows = [local({ syncState: 'done', cloudId: 'cloud-9' }), local({ id: 'local-2' })]
    const visible = hideSyncedLocals(rows, new Set(['cloud-9']))
    expect(visible.map((r) => r.id)).toEqual(['local-2'])
  })

  it('keeps a done row when its twin was NOT fetched (offline copy stays visible)', () => {
    const rows = [local({ syncState: 'done', cloudId: 'cloud-9' })]
    expect(hideSyncedLocals(rows, new Set())).toHaveLength(1)
  })
})
