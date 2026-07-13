import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  onUsageLimit,
  showUsageLimit,
  dismissUsageLimit,
  maybeTriggerChatQuotaPopup,
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

beforeEach(() => __resetUsageLimitSession())

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
