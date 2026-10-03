import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const state = vi.hoisted(() => ({
  epoch: 1,
  owner: 'a' as string | null,
  feed: vi.fn(),
  outcome: vi.fn(),
  present: vi.fn()
}))
vi.mock('../../renderer/src/lib/omiApi.generated', () => ({
  get_proactivity_feed: state.feed,
  record_proactivity_outcome: state.outcome,
  OmiApiError: class extends Error {
    constructor(
      public status: number,
      public response?: Response
    ) {
      super()
    }
  }
}))
vi.mock('../assistants/core/session', () => ({
  getSessionEpoch: () => state.epoch,
  getBackendSession: () =>
    state.owner ? { token: state.owner, apiBase: 'https://example.invalid' } : null,
  tokenUid: (token: string) => token || null,
  isSessionExpired: () => false,
  pullFreshSession: vi.fn()
}))
vi.mock('./notificationAdapter', () => ({ presentProactivityNotification: state.present }))
import { ProactivityFeedConsumer } from './feedConsumer'
import { OmiApiError } from '../../renderer/src/lib/omiApi.generated'
const item = { id: 'item', created_at: '2026-10-03T12:00:00Z', acted: false, dismissed: false }
const response = { enabled: true, items: [item], server_time: '2026-10-03T13:00:00Z' }
let directory: string, file: string, now: number
beforeEach(() => {
  vi.useFakeTimers()
  directory = mkdtempSync(join(tmpdir(), 'pv2-consumer-'))
  file = join(directory, 'journal.json')
  now = 2_000_000
  vi.spyOn(Date, 'now').mockImplementation(() => now)
  state.owner = 'a'
  state.epoch = 1
  state.feed.mockReset().mockResolvedValue(response)
  state.outcome.mockReset().mockResolvedValue({ recorded: true })
  state.present.mockReset().mockReturnValue(true)
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  rmSync(directory, { recursive: true, force: true })
})
describe('feed consumer transport and owner boundary', () => {
  it('refreshes on owner-matched v2 wakeups even inside the foreground debounce', async () => {
    const consumer = new ProactivityFeedConsumer(file, async () => true)
    await consumer.refresh()
    const event = {
      type: 'proactivity_v2',
      item_id: 'item',
      target_kind: 'conversation',
      target_id: 'c'
    }
    consumer.handleListenEvent('b', event)
    consumer.handleListenEvent('a', { type: 'proactive_message', app_id: 'mentor' })
    expect(state.feed).toHaveBeenCalledTimes(1)
    consumer.handleListenEvent('a', event)
    await vi.runAllTicks()
    expect(state.feed).toHaveBeenCalledTimes(2)
  })
  it('coalesces a v2 wakeup received during a pending feed request', async () => {
    let finish!: (value: typeof response) => void
    state.feed.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    const consumer = new ProactivityFeedConsumer(file, async () => true)
    const poll = consumer.refresh()
    consumer.handleListenEvent('a', {
      type: 'proactivity_v2',
      item_id: 'item',
      target_kind: 'conversation',
      target_id: 'c'
    })
    finish(response)
    await poll
    expect(state.feed).toHaveBeenCalledTimes(2)
  })

  it('retries a failed durable outcome and never shows the item again after relaunch', async () => {
    const first = new ProactivityFeedConsumer(file, async () => true)
    await first.refresh()
    const context = state.present.mock.calls[0][1]
    context.onOutcome('item', {
      action: 'shown',
      channel: 'feed',
      surface: 'windows',
      event_id: 'stable-event'
    })
    now += 600_000
    state.outcome.mockRejectedValueOnce(new Error('offline'))
    await first.refresh()
    expect(state.outcome).toHaveBeenCalledTimes(1)
    now += 600_000
    const restarted = new ProactivityFeedConsumer(file, async () => true)
    await restarted.refresh()
    expect(state.outcome).toHaveBeenCalledTimes(2)
    expect(state.outcome.mock.calls[0][2]).toEqual(state.outcome.mock.calls[1][2])
    expect(state.present).toHaveBeenCalledTimes(1)
    now += 600_000
    await restarted.refresh()
    expect(state.outcome).toHaveBeenCalledTimes(2)
  })
  it('retries pending outcomes in the background without polling another feed', async () => {
    const consumer = new ProactivityFeedConsumer(file, async () => true)
    await consumer.refresh()
    state.present.mock.calls[0][1].onOutcome('item', {
      action: 'shown',
      channel: 'feed',
      surface: 'windows',
      event_id: 'timer-event'
    })
    now += 30_000
    await vi.advanceTimersByTimeAsync(30_000)
    expect(state.outcome).toHaveBeenCalledOnce()
    expect(state.feed).toHaveBeenCalledOnce()
  })
  it('honors Retry-After across foreground refreshes', async () => {
    const consumer = new ProactivityFeedConsumer(file, async () => true)
    await consumer.refresh()
    state.present.mock.calls[0][1].onOutcome('item', {
      action: 'shown',
      channel: 'feed',
      surface: 'windows',
      event_id: 'limited'
    })
    state.outcome.mockRejectedValueOnce(
      new OmiApiError(429, new Response('', { headers: { 'Retry-After': '3600' } }))
    )
    now += 30_000
    await vi.advanceTimersByTimeAsync(30_000)
    expect(state.outcome).toHaveBeenCalledOnce()
    now += 600_000
    await consumer.refresh()
    expect(state.outcome).toHaveBeenCalledOnce()
    now += 3_000_000
    await consumer.refresh()
    expect(state.outcome).toHaveBeenCalledTimes(2)
  })
  it('drops delayed feed responses after owner switch', async () => {
    let resolve!: (value: unknown) => void
    state.feed.mockReturnValueOnce(
      new Promise((r) => {
        resolve = r
      })
    )
    const consumer = new ProactivityFeedConsumer(file, async () => true)
    const work = consumer.refresh()
    state.owner = 'b'
    state.epoch++
    resolve(response)
    await work
    expect(state.present).not.toHaveBeenCalled()
  })
  it('purges receipts and rejects callbacks from the signed-out session', async () => {
    const consumer = new ProactivityFeedConsumer(file, async () => true)
    await consumer.refresh()
    const context = state.present.mock.calls[0][1]
    state.owner = null
    state.epoch++
    consumer.sessionChanged()
    context.onOutcome('item', {
      action: 'shown',
      channel: 'feed',
      surface: 'windows',
      event_id: 'stale'
    })
    expect(existsSync(file)).toBe(false)
  })
})
