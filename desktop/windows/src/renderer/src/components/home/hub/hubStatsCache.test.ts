import { describe, it, expect } from 'vitest'
import { readStats, mergeStats, overlay } from './hubStatsCache'
import type { HubStatCounts } from './HubStatRibbon'

// The pure core of the Hub stat-ribbon cache. These tests pin two things:
//   1. stale-while-revalidate — a cached number renders, a fresh one overwrites it;
//   2. the CROSS-ACCOUNT GUARD — counts are scoped to the account that wrote them
//      and must never bleed into a different signed-in user on the same machine.

const UNKNOWN: HubStatCounts = {
  conversations: null,
  conversationsAtLeast: false,
  tasks: null,
  memories: null,
  screenshots: null
}

const counts = (p: Partial<HubStatCounts>): HubStatCounts => ({ ...UNKNOWN, ...p })

describe('hubStatsCache — read', () => {
  it('returns the unknown state for a missing or unparseable blob', () => {
    expect(readStats(null, 'user-a')).toEqual(UNKNOWN)
    expect(readStats('not json', 'user-a')).toEqual(UNKNOWN)
  })

  it('returns the stored counts for the owning uid', () => {
    const blob = mergeStats(null, 'user-a', counts({ tasks: 5, memories: 42 }))
    expect(readStats(blob, 'user-a')).toEqual(counts({ tasks: 5, memories: 42 }))
  })

  it('round-trips the conversations "+" floor flag', () => {
    const blob = mergeStats(
      null,
      'user-a',
      counts({ conversations: 100, conversationsAtLeast: true })
    )
    expect(readStats(blob, 'user-a')).toEqual(
      counts({ conversations: 100, conversationsAtLeast: true })
    )
  })

  it('coerces malformed/negative counts to unknown, never a wrong number', () => {
    const blob = JSON.stringify({ uid: 'user-a', conversations: -3, tasks: 'nope', memories: 7 })
    expect(readStats(blob, 'user-a')).toEqual(counts({ memories: 7 }))
  })
})

describe('hubStatsCache — merge (last-known-good per cell)', () => {
  it('keeps a cached cell when the fresh value is still unknown (null)', () => {
    let blob = mergeStats(null, 'user-a', counts({ tasks: 5, memories: 42 }))
    // A later render where only memories re-resolved; tasks is null this pass.
    blob = mergeStats(blob, 'user-a', counts({ memories: 43 }))
    expect(readStats(blob, 'user-a')).toEqual(counts({ tasks: 5, memories: 43 }))
  })

  it('overwrites a cached cell when a fresh value lands', () => {
    let blob = mergeStats(null, 'user-a', counts({ tasks: 5 }))
    blob = mergeStats(blob, 'user-a', counts({ tasks: 9 }))
    expect(readStats(blob, 'user-a')).toEqual(counts({ tasks: 9 }))
  })

  it('moves the conversations count and its "+" flag together', () => {
    // Cache a floored 100+, then a render where conversations is unknown must NOT
    // strand a true "+" flag on a missing number.
    let blob = mergeStats(
      null,
      'user-a',
      counts({ conversations: 100, conversationsAtLeast: true })
    )
    blob = mergeStats(blob, 'user-a', counts({ tasks: 1 })) // conversations null this pass
    expect(readStats(blob, 'user-a')).toEqual(
      counts({ conversations: 100, conversationsAtLeast: true, tasks: 1 })
    )
  })
})

describe('hubStatsCache — cross-account guard', () => {
  it('does NOT expose one account’s counts to a different signed-in uid', () => {
    const blob = mergeStats(null, 'user-a', counts({ tasks: 5, memories: 42 }))
    // Same machine, different account signs in — must see unknown, never user-a's numbers.
    expect(readStats(blob, 'user-b')).toEqual(UNKNOWN)
  })

  it('treats a signed-out (null uid) reader as a different account', () => {
    const blob = mergeStats(null, 'user-a', counts({ tasks: 5 }))
    expect(readStats(blob, null)).toEqual(UNKNOWN)
  })

  it('discards the prior owner’s counts when a new account writes', () => {
    const aBlob = mergeStats(null, 'user-a', counts({ tasks: 5, memories: 42 }))
    // user-b's hub resolves its own numbers on the same machine.
    const bBlob = mergeStats(aBlob, 'user-b', counts({ tasks: 1 }))
    // user-b sees only their own; user-a's counts are gone (not merged in).
    expect(readStats(bBlob, 'user-b')).toEqual(counts({ tasks: 1 }))
    // And user-a, if they sign back in, no longer sees the overwritten blob.
    expect(readStats(bBlob, 'user-a')).toEqual(UNKNOWN)
  })
})

describe('hubStatsCache — overlay (stale-while-revalidate display)', () => {
  it('shows cached values wherever the live fetch has not resolved', () => {
    const cached = counts({ conversations: 12, tasks: 5, memories: 42, screenshots: 8 })
    expect(overlay(cached, UNKNOWN)).toEqual(cached)
  })

  it('prefers a live value the moment it lands, per cell', () => {
    const cached = counts({ conversations: 12, tasks: 5, memories: 42, screenshots: 8 })
    const live = counts({ tasks: 6 }) // only tasks re-fetched so far
    expect(overlay(cached, live)).toEqual(
      counts({ conversations: 12, tasks: 6, memories: 42, screenshots: 8 })
    )
  })

  it('takes the live conversations "+" flag with the live count, not the cached flag', () => {
    const cached = counts({ conversations: 100, conversationsAtLeast: true })
    const live = counts({ conversations: 3, conversationsAtLeast: false })
    expect(overlay(cached, live)).toEqual(counts({ conversations: 3, conversationsAtLeast: false }))
  })
})
