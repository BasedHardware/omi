import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the renderer BYOK cache so we can drive the "BYOK active" branch. Default
// inactive, matching a free (non-BYOK) user; individual tests flip it on.
const h = vi.hoisted(() => ({ isByokActiveCached: vi.fn(() => false) }))
vi.mock('./byokKeys', () => ({ isByokActiveCached: h.isByokActiveCached }))

import {
  onUsageLimit,
  showUsageLimit,
  dismissUsageLimit,
  maybeTriggerChatQuotaPopup,
  maybeTriggerTranscriptionQuotaPopup,
  __resetUsageLimitSession,
  type UsageLimitReason
} from './usageLimit'
import type { ChatUsageQuota } from './omiApi.generated'

const quota = (p: Partial<ChatUsageQuota>): ChatUsageQuota => ({
  plan: 'basic',
  plan_type: 'free',
  unit: 'questions',
  used: 0,
  ...p
})

beforeEach(() => {
  __resetUsageLimitSession()
  h.isByokActiveCached.mockReturnValue(false)
})

describe('usage-limit pub/sub', () => {
  it('delivers the current reason to new and existing subscribers', () => {
    const seen: (UsageLimitReason | null)[] = []
    const off = onUsageLimit((r) => seen.push(r))
    expect(seen).toEqual([null]) // immediate current value
    showUsageLimit('transcription')
    dismissUsageLimit()
    off()
    expect(seen).toEqual([null, 'transcription', null])
  })
})

describe('maybeTriggerChatQuotaPopup', () => {
  it('shows the popup once when the quota is exhausted', async () => {
    const seen: (UsageLimitReason | null)[] = []
    onUsageLimit((r) => seen.push(r))
    const fetchQuota = vi.fn().mockResolvedValue(quota({ used: 30, limit: 30, allowed: false }))

    expect(await maybeTriggerChatQuotaPopup(fetchQuota)).toBe(true)
    expect(seen.at(-1)).toBe('chat')

    // Second call in the same session is a no-op (no nagging).
    expect(await maybeTriggerChatQuotaPopup(fetchQuota)).toBe(false)
    expect(fetchQuota).toHaveBeenCalledTimes(1)
  })

  it('does nothing when the quota still allows sending', async () => {
    const fetchQuota = vi.fn().mockResolvedValue(quota({ used: 5, limit: 30, allowed: true }))
    expect(await maybeTriggerChatQuotaPopup(fetchQuota)).toBe(false)
  })

  it('stays silent when the quota probe fails', async () => {
    const fetchQuota = vi.fn().mockRejectedValue(new Error('network'))
    expect(await maybeTriggerChatQuotaPopup(fetchQuota)).toBe(false)
  })
})

describe('maybeTriggerTranscriptionQuotaPopup', () => {
  // The message the capture window surfaces on a 1008 free-quota close.
  const QUOTA_ERR =
    'free Omi transcription quota is used up (1008) — add an Omi subscription or sign in with an entitled account to keep transcribing'

  it('raises the transcription popup once when a quota-exhausted error status arrives', () => {
    const seen: (UsageLimitReason | null)[] = []
    onUsageLimit((r) => seen.push(r))

    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(true)
    expect(seen.at(-1)).toBe('transcription')

    // Repeated error callbacks for the same exhaustion must not re-raise it.
    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(false)
    expect(seen.filter((r) => r === 'transcription')).toHaveLength(1)
  })

  it('does not raise the popup for a normal (non-quota) error', () => {
    const seen: (UsageLimitReason | null)[] = []
    onUsageLimit((r) => seen.push(r))
    expect(maybeTriggerTranscriptionQuotaPopup('error', 'microphone unavailable')).toBe(false)
    expect(maybeTriggerTranscriptionQuotaPopup('error', undefined)).toBe(false)
    expect(seen).toEqual([null]) // only the immediate current value; never 'transcription'
  })

  it('does not raise the popup for a healthy status', () => {
    expect(maybeTriggerTranscriptionQuotaPopup('live')).toBe(false)
    expect(maybeTriggerTranscriptionQuotaPopup('connecting')).toBe(false)
  })

  it('re-arms after recovery so a later exhaustion shows again', () => {
    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(true)
    // A non-error status re-arms the latch...
    expect(maybeTriggerTranscriptionQuotaPopup('live')).toBe(false)
    // ...so a fresh exhaustion raises the popup a second time.
    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(true)
  })

  it('never paywalls a BYOK user — no popup on a quota error while BYOK is active', () => {
    h.isByokActiveCached.mockReturnValue(true)
    const seen: (UsageLimitReason | null)[] = []
    onUsageLimit((r) => seen.push(r))
    // A quota-exhausted error that WOULD raise the popup for a free user...
    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(false)
    expect(seen).toEqual([null]) // only the immediate value; never 'transcription'
  })

  it('still shows the popup for a non-BYOK (free) user on the same quota error', () => {
    h.isByokActiveCached.mockReturnValue(false)
    const seen: (UsageLimitReason | null)[] = []
    onUsageLimit((r) => seen.push(r))
    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(true)
    expect(seen.at(-1)).toBe('transcription')
  })

  it('does not consume the latch while BYOK is active — a later exhaustion after BYOK clears still shows', () => {
    h.isByokActiveCached.mockReturnValue(true)
    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(false)
    // BYOK is cleared (keys removed / different account); the guard no longer
    // suppresses and the still-armed latch lets the genuine exhaustion show.
    h.isByokActiveCached.mockReturnValue(false)
    expect(maybeTriggerTranscriptionQuotaPopup('error', QUOTA_ERR)).toBe(true)
  })
})
