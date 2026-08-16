// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  enqueueFeedback,
  loadOutbox,
  matchesPendingSuppression,
  purgeMismatchedGeneration,
  removeFeedback,
  replayOutbox,
  type PendingFeedback
} from './feedbackOutbox'

vi.mock('../persistentCache', () => ({ getCacheUid: () => 'uid-1' }))

const entry = (over: Partial<PendingFeedback> = {}): PendingFeedback => ({
  request: {
    action: 'dismiss',
    subject_kind: 'candidate',
    subject_id: 'c-1',
    intervention_id: 'iv-1',
    reason: null,
    later_until: null,
    context_snapshot_hash: null
  },
  idempotencyKey: 'wmn:iv-1:dismiss:none',
  accountGeneration: 3,
  ...over
})

beforeEach(() => {
  window.localStorage.clear()
})

describe('outbox persistence', () => {
  it('is owner-scoped under whatMattersNowFeedbackOutbox.v1.<owner>', () => {
    enqueueFeedback(entry())
    expect(window.localStorage.getItem('whatMattersNowFeedbackOutbox.v1.uid-1')).toBeTruthy()
    expect(loadOutbox('someone-else')).toEqual([])
  })

  it('write-ahead enqueue overwrites the same idempotency key instead of duplicating', () => {
    enqueueFeedback(entry())
    enqueueFeedback(entry({ accountGeneration: 4 }))
    const entries = loadOutbox()
    expect(entries).toHaveLength(1)
    expect(entries[0].accountGeneration).toBe(4)
  })

  it('remove deletes exactly the given key', () => {
    enqueueFeedback(entry())
    enqueueFeedback(entry({ idempotencyKey: 'wmn:iv-2:do-now' }))
    removeFeedback('wmn:iv-1:dismiss:none')
    expect(loadOutbox().map((e) => e.idempotencyKey)).toEqual(['wmn:iv-2:do-now'])
  })

  it('survives a corrupt payload by treating it as empty', () => {
    window.localStorage.setItem('whatMattersNowFeedbackOutbox.v1.uid-1', '{not json')
    expect(loadOutbox()).toEqual([])
  })
})

describe('generation purge', () => {
  it('drops entries whose generation no longer matches, silently and permanently', () => {
    enqueueFeedback(entry({ idempotencyKey: 'a', accountGeneration: 3 }))
    enqueueFeedback(entry({ idempotencyKey: 'b', accountGeneration: 4 }))
    const survivors = purgeMismatchedGeneration(4)
    expect(survivors.map((e) => e.idempotencyKey)).toEqual(['b'])
    expect(loadOutbox().map((e) => e.idempotencyKey)).toEqual(['b'])
  })
})

describe('pending suppression matching', () => {
  const row = { interventionId: 'iv-1', feedbackSubjectKind: 'candidate', feedbackSubjectId: 'c-1' }

  it('matches a pending dismiss by intervention id', () => {
    expect(matchesPendingSuppression([entry()], row)).toBe(true)
  })

  it('matches a pending later by subject kind + id even with a different intervention', () => {
    const later = entry({
      idempotencyKey: 'k2',
      request: { ...entry().request, action: 'later', intervention_id: 'iv-OTHER' }
    })
    expect(matchesPendingSuppression([later], row)).toBe(true)
  })

  it('never suppresses on do_now or accept feedback', () => {
    const doNow = entry({
      idempotencyKey: 'k3',
      request: { ...entry().request, action: 'do_now' }
    })
    expect(matchesPendingSuppression([doNow], row)).toBe(false)
  })

  it('does not match an unrelated row', () => {
    expect(
      matchesPendingSuppression([entry()], {
        interventionId: 'iv-9',
        feedbackSubjectKind: 'task',
        feedbackSubjectId: 't-9'
      })
    ).toBe(false)
  })
})

describe('replay', () => {
  it('is one sequential pass: successes leave, failures stay, order preserved', async () => {
    enqueueFeedback(entry({ idempotencyKey: 'a' }))
    enqueueFeedback(entry({ idempotencyKey: 'b' }))
    enqueueFeedback(entry({ idempotencyKey: 'c' }))
    const sent: string[] = []
    const delivered = await replayOutbox(async (e) => {
      sent.push(e.idempotencyKey)
      if (e.idempotencyKey === 'b') throw new Error('down')
    })
    expect(sent).toEqual(['a', 'b', 'c'])
    expect(delivered).toBe(2)
    expect(loadOutbox().map((e) => e.idempotencyKey)).toEqual(['b'])
  })

  it('entries enqueued during the pass survive it', async () => {
    enqueueFeedback(entry({ idempotencyKey: 'a' }))
    await replayOutbox(async () => {
      enqueueFeedback(entry({ idempotencyKey: 'late' }))
    })
    expect(loadOutbox().map((e) => e.idempotencyKey)).toEqual(['late'])
  })

  it('stops sending when the owner scope goes stale mid-pass and keeps the rest', async () => {
    enqueueFeedback(entry({ idempotencyKey: 'a' }))
    enqueueFeedback(entry({ idempotencyKey: 'b' }))
    let current = true
    const sent: string[] = []
    await replayOutbox(
      async (e) => {
        sent.push(e.idempotencyKey)
        current = false // the account switches after the first send
      },
      'uid-1',
      () => current
    )
    expect(sent).toEqual(['a'])
    // The removal write is also skipped under a stale scope, so nothing of the
    // old owner's queue is mutated from the new session.
    expect(loadOutbox('uid-1').map((e) => e.idempotencyKey)).toEqual(['a', 'b'])
  })

  it('drops malformed persisted entries instead of replaying them forever', () => {
    window.localStorage.setItem(
      'whatMattersNowFeedbackOutbox.v1.uid-1',
      JSON.stringify([
        { idempotencyKey: 'bad', accountGeneration: 3, request: { nope: true } },
        entry({ idempotencyKey: 'good' })
      ])
    )
    expect(loadOutbox('uid-1').map((e) => e.idempotencyKey)).toEqual(['good'])
  })
})
