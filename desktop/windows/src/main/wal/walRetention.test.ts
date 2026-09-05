import { describe, it, expect } from 'vitest'
import { DEFAULT_RETENTION, planRetention, totalBytes } from './walRetention'
import { makeWalEntry, type WalEntry, type WalStatus } from '../../shared/wal'

const DAY = 24 * 60 * 60
const NOW = 1_724_000_000

const entry = (timerStart: number, status: WalStatus, sizeBytes: number): WalEntry =>
  makeWalEntry({
    timerStart,
    codec: 'pcm16',
    seconds: 60,
    frameSize: 160,
    totalFrames: 240,
    device: 'mic',
    status,
    storage: 'disk',
    filePath: `audio_mic_pcm16_16000_1_fs160_${timerStart}.bin`,
    sizeBytes
  })

describe('planRetention', () => {
  it('releases confirmed recordings that aged out', () => {
    const old = entry(NOW - 20 * DAY, 'synced', 100)
    const recent = entry(NOW - 1 * DAY, 'synced', 100)
    const plan = planRetention([old, recent], { maxBytes: 10_000, retentionDays: 14 }, NOW)
    expect(plan.expired.map((e) => e.timerStart)).toEqual([old.timerStart])
    expect(plan.overBudget).toEqual([])
    expect(plan.atCapacity).toBe(false)
  })

  it('never releases audio the server has not confirmed, however old', () => {
    // These bytes are the only copy of that audio.
    const statuses: WalStatus[] = ['miss', 'inProgress', 'uploaded', 'outsideRecoveryWindow']
    const entries = statuses.map((status, i) => entry(NOW - 100 * DAY - i, status, 100))
    const plan = planRetention(entries, { maxBytes: 10, retentionDays: 1 }, NOW)
    expect(plan.expired).toEqual([])
    expect(plan.overBudget).toEqual([])
    // The log cannot get under budget without deleting irreplaceable audio, so
    // it reports being full instead of doing it.
    expect(plan.atCapacity).toBe(true)
  })

  it('releases the oldest confirmed recordings to get back under budget', () => {
    const entries = [
      entry(NOW - 5 * DAY, 'synced', 400),
      entry(NOW - 4 * DAY, 'synced', 400),
      entry(NOW - 3 * DAY, 'synced', 400)
    ]
    const plan = planRetention(entries, { maxBytes: 500, retentionDays: 30 }, NOW)
    // Oldest first, and only as many as the budget needs.
    expect(plan.overBudget.map((e) => e.timerStart)).toEqual([NOW - 5 * DAY, NOW - 4 * DAY])
    expect(plan.bytesAfter).toBe(400)
    expect(plan.atCapacity).toBe(false)
  })

  it('counts unconfirmed bytes against the budget without releasing them', () => {
    const pending = entry(NOW - 1 * DAY, 'miss', 900)
    const confirmed = entry(NOW - 2 * DAY, 'synced', 400)
    const plan = planRetention([pending, confirmed], { maxBytes: 1000, retentionDays: 30 }, NOW)
    // Releasing the confirmed one gets under budget; the pending one stays.
    expect(plan.overBudget.map((e) => e.timerStart)).toEqual([confirmed.timerStart])
    expect(plan.bytesAfter).toBe(900)
    expect(plan.atCapacity).toBe(false)
  })

  it('expiry runs before the budget so aged audio is not counted twice', () => {
    const expired = entry(NOW - 40 * DAY, 'synced', 800)
    const recent = entry(NOW - 1 * DAY, 'synced', 300)
    const plan = planRetention([expired, recent], { maxBytes: 500, retentionDays: 14 }, NOW)
    expect(plan.expired.map((e) => e.timerStart)).toEqual([expired.timerStart])
    // Once the aged one is gone the rest already fits.
    expect(plan.overBudget).toEqual([])
    expect(plan.bytesAfter).toBe(300)
  })

  it('does nothing when everything fits', () => {
    const plan = planRetention([entry(NOW, 'synced', 10)], DEFAULT_RETENTION, NOW)
    expect(plan).toMatchObject({ expired: [], overBudget: [], atCapacity: false, bytesAfter: 10 })
  })

  it('handles an empty log', () => {
    expect(planRetention([], DEFAULT_RETENTION, NOW)).toMatchObject({
      expired: [],
      overBudget: [],
      atCapacity: false,
      bytesAfter: 0
    })
  })
})

describe('totalBytes', () => {
  it('sums what the log is holding', () => {
    expect(totalBytes([entry(1, 'miss', 100), entry(2, 'synced', 250)])).toBe(350)
    expect(totalBytes([])).toBe(0)
  })
})
