import { describe, it, expect } from 'vitest'
import { readCounts, mergeCounts } from './onboardingImportCounts'

// The pure core of the onboarding import-count cache. These tests pin the
// CROSS-ACCOUNT GUARD: an import tally is scoped to the account that wrote it and
// must never bleed into a different signed-in user on the same machine.

describe('onboardingImportCounts — read', () => {
  it('returns zeros for a missing or unparseable blob', () => {
    expect(readCounts(null, 'user-a')).toEqual({ chatgpt: 0, claude: 0 })
    expect(readCounts('not json', 'user-a')).toEqual({ chatgpt: 0, claude: 0 })
  })

  it('returns the stored counts for the owning uid', () => {
    const blob = mergeCounts(null, 'user-a', 'chatgpt', 14)
    expect(readCounts(blob, 'user-a')).toEqual({ chatgpt: 14, claude: 0 })
  })

  it('coerces malformed/negative counts to zero', () => {
    const blob = JSON.stringify({ uid: 'user-a', chatgpt: -3, claude: 'nope' })
    expect(readCounts(blob, 'user-a')).toEqual({ chatgpt: 0, claude: 0 })
  })
})

describe('onboardingImportCounts — cross-account guard', () => {
  it('does NOT expose one account’s counts to a different signed-in uid', () => {
    const blob = mergeCounts(null, 'user-a', 'chatgpt', 14)
    // Same machine, different account signs in — must see zero, never user-a's 14.
    expect(readCounts(blob, 'user-b')).toEqual({ chatgpt: 0, claude: 0 })
  })

  it('treats a signed-out (null uid) reader as a different account', () => {
    const blob = mergeCounts(null, 'user-a', 'claude', 7)
    expect(readCounts(blob, null)).toEqual({ chatgpt: 0, claude: 0 })
  })

  it('discards the prior owner’s tally when a new account writes', () => {
    const aBlob = mergeCounts(null, 'user-a', 'chatgpt', 14)
    // user-b imports Claude memories on the same machine.
    const bBlob = mergeCounts(aBlob, 'user-b', 'claude', 3)
    // user-b sees only their own import; user-a's chatgpt count is gone.
    expect(readCounts(bBlob, 'user-b')).toEqual({ chatgpt: 0, claude: 3 })
    // And user-a, if they sign back in, no longer sees the (now overwritten) tally.
    expect(readCounts(bBlob, 'user-a')).toEqual({ chatgpt: 0, claude: 0 })
  })

  it('accumulates both sources for the same uid across writes', () => {
    let blob = mergeCounts(null, 'user-a', 'chatgpt', 12)
    blob = mergeCounts(blob, 'user-a', 'claude', 5)
    expect(readCounts(blob, 'user-a')).toEqual({ chatgpt: 12, claude: 5 })
  })
})
