import { describe, it, expect, vi } from 'vitest'
import type { ChatUsageQuota } from './omiApi.generated'
import { createChatQuotaGate, isLimitReached, limitMessage } from './chatQuotaGate'

// The bar's pre-send chat-quota gate (port of macOS FloatingBarUsageLimiter).
// The bug it closes: the bar's send path had NO gate, so a user over their
// monthly limit could keep asking from the bar (the main window only probes the
// quota AFTER a send). Every send from the bar — typed and PTT — now checks here.

const quota = (over: Partial<ChatUsageQuota> = {}): ChatUsageQuota => ({
  plan: 'Free',
  plan_type: 'basic',
  unit: 'questions',
  used: 0,
  limit: 30,
  percent: 0,
  allowed: true,
  reset_at: null,
  ...over
})

describe('isLimitReached', () => {
  it('blocks when the server says allowed=false — whatever the unit', () => {
    expect(isLimitReached(quota({ allowed: false }), 0)).toBe(true)
    expect(isLimitReached(quota({ allowed: false, unit: 'cost_usd', limit: 20 }), 0)).toBe(true)
  })

  it('blocks locally once used + sends-since-sync reaches a questions limit', () => {
    // The server snapshot still says allowed (it predates these sends), but the
    // optimistic delta has carried the user over — Mac blocks here too, so
    // back-to-back sends between two syncs cannot slip past the cap.
    expect(isLimitReached(quota({ used: 28 }), 1)).toBe(false)
    expect(isLimitReached(quota({ used: 28 }), 2)).toBe(true)
  })

  it('trusts the server alone for cost_usd plans (no client-side spend estimate)', () => {
    expect(isLimitReached(quota({ unit: 'cost_usd', limit: 20, used: 19.5 }), 5)).toBe(false)
  })

  it('never blocks on an unlimited (limit: null) plan — e.g. BYOK, which the backend exempts', () => {
    expect(isLimitReached(quota({ plan: 'Free (BYOK)', limit: null, used: 999 }), 3)).toBe(false)
  })

  it('fails OPEN with no snapshot — a network blip must not lock the user out', () => {
    expect(isLimitReached(null, 99)).toBe(false)
  })
})

describe('limitMessage', () => {
  it('reads Mac verbatim, per unit', () => {
    expect(limitMessage(quota({ used: 30 }))).toBe(
      "You've reached 30 Free messages this month. Upgrade to keep chatting without restrictions."
    )
    expect(limitMessage(quota({ unit: 'cost_usd', limit: 20, plan: 'Architect' }))).toContain(
      'your $20 Architect monthly spend limit'
    )
    expect(limitMessage(null)).toContain('your monthly free message limit')
  })
})

describe('createChatQuotaGate', () => {
  it('blocks a send once the quota is exhausted, and reports the limit line', async () => {
    const gate = createChatQuotaGate(async () => quota({ allowed: false, used: 30 }))
    await gate.sync()
    expect(await gate.check()).toEqual({
      blocked: true,
      message: limitMessage(quota({ allowed: false, used: 30 }))
    })
  })

  it('lets an in-quota send through untouched', async () => {
    const gate = createChatQuotaGate(async () => quota({ used: 2 }))
    await gate.sync()
    expect(await gate.check()).toEqual({ blocked: false })
  })

  it('keeps the send path OFF the network — one cold fetch, then a cached verdict', async () => {
    const fetchQuota = vi.fn(async () => quota({ used: 2 }))
    const gate = createChatQuotaGate(fetchQuota)
    await gate.sync()
    expect(fetchQuota).toHaveBeenCalledTimes(1)
    // Warm sends: no further round trip per send/keystroke.
    for (let i = 0; i < 5; i++) {
      expect(await gate.check()).toEqual({ blocked: false })
      gate.recordQuery()
    }
    expect(fetchQuota).toHaveBeenCalledTimes(1)
  })

  it('cold start (no snapshot yet) forces exactly ONE sync so an over-cap user gets no free send', async () => {
    const fetchQuota = vi.fn(async () => quota({ allowed: false }))
    const gate = createChatQuotaGate(fetchQuota)
    // No sync() first — this is the very first send after launch.
    expect(await gate.check()).toMatchObject({ blocked: true })
    expect(fetchQuota).toHaveBeenCalledTimes(1)
  })

  it('fails OPEN when the quota fetch errors — the server stays the real enforcer', async () => {
    const gate = createChatQuotaGate(async () => {
      throw new Error('offline')
    })
    await expect(gate.sync()).resolves.toBeUndefined()
    expect(await gate.check()).toEqual({ blocked: false })
  })

  it('counts sends since the last sync, then blocks — and a fresh sync resets the count', async () => {
    const gate = createChatQuotaGate(async () => quota({ used: 29 }))
    await gate.sync()
    expect(await gate.check()).toEqual({ blocked: false })
    gate.recordQuery() // 29 + 1 === 30
    expect(await gate.check()).toMatchObject({ blocked: true })
    // The server's next snapshot is the truth again (the user upgraded).
    gate.applyQuota(quota({ plan: 'Neo', used: 30, limit: 1000 }))
    expect(await gate.check()).toEqual({ blocked: false })
  })
})
