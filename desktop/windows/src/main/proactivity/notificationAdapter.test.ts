import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProactivityFeedItem } from '../../renderer/src/lib/omiApi.generated'
const state = vi.hoisted(() => ({ epoch: 1, notify: vi.fn() }))
vi.mock('../assistants/core/session', () => ({ getSessionEpoch: () => state.epoch }))
vi.mock('../assistants/core/notify', () => ({ notifyProactive: state.notify }))
import { presentProactivityNotification, proactivityEventID } from './notificationAdapter'
const item: ProactivityFeedItem = {
  id: 'item-1',
  producer: 'future_registered_producer',
  created_at: '2026-10-03T12:00:00Z',
  title: 'Follow up',
  body: 'Synthetic fixture',
  acted: false,
  dismissed: false,
  feedback: 'none',
  target: { kind: 'action_item', id: 'task-1' }
}
function context() {
  return {
    ownerID: 'owner',
    epoch: 1,
    isOwnerCurrent: () => true,
    hasBeenPresented: () => false,
    onOutcome: vi.fn(),
    openTarget: vi.fn().mockResolvedValue(true)
  }
}
beforeEach(() => {
  state.epoch = 1
  state.notify.mockReset().mockReturnValue(true)
})
describe('v2 shared-toast adapter', () => {
  it('renders both producer fixtures and opens their canonical target', async () => {
    const fixture = JSON.parse(
      readFileSync(resolve(process.cwd(), '../../contracts/parity/proactivity_v2.json'), 'utf8')
    )
    for (const producerItem of fixture.producer_items as ProactivityFeedItem[]) {
      const ctx = context()
      expect(presentProactivityNotification(producerItem, ctx)).toBe(true)
      const hooks = state.notify.mock.calls.at(-1)![2].deliveryHooks
      hooks.onPresented()
      hooks.onOpened()
      await Promise.resolve()
      expect(ctx.openTarget).toHaveBeenCalledWith(producerItem.target)
      expect(ctx.onOutcome.mock.calls.map((call) => call[1].action)).toEqual(['shown', 'opened'])
    }
  })

  it('reports actual presentation once and opens the typed target', async () => {
    const ctx = context()
    expect(presentProactivityNotification(item, ctx)).toBe(true)
    expect(ctx.onOutcome).not.toHaveBeenCalled()
    const hooks = state.notify.mock.calls[0][2].deliveryHooks
    hooks.onPresented()
    hooks.onPresented()
    hooks.onOpened()
    await Promise.resolve()
    expect(ctx.onOutcome.mock.calls.map((call) => call[1].action)).toEqual(['shown', 'opened'])
    expect(ctx.openTarget).toHaveBeenCalledWith(item.target)
  })
  it('does not report shown for suppression or act after a session change', () => {
    const ctx = context()
    state.notify.mockReturnValue(false)
    expect(presentProactivityNotification(item, ctx)).toBe(false)
    expect(ctx.onOutcome).not.toHaveBeenCalled()
    const hooks = state.notify.mock.calls[0][2].deliveryHooks
    state.epoch = 2
    hooks.onPresented()
    hooks.onOpened()
    hooks.onDismissed('dismissed')
    expect(ctx.onOutcome).not.toHaveBeenCalled()
    expect(ctx.openTarget).not.toHaveBeenCalled()
  })
  it('rejects handled and durably shown items before shared delivery', () => {
    expect(presentProactivityNotification({ ...item, dismissed: true }, context())).toBe(false)
    expect(
      presentProactivityNotification(item, { ...context(), hasBeenPresented: () => true })
    ).toBe(false)
    expect(state.notify).not.toHaveBeenCalled()
  })
  it('ignores timeout, accepts explicit feedback, and waits for successful navigation', async () => {
    const ctx = context()
    ctx.openTarget.mockResolvedValue(false)
    presentProactivityNotification(item, ctx)
    const hooks = state.notify.mock.calls[0][2].deliveryHooks
    hooks.onDismissed('timeout')
    hooks.onOpened()
    await Promise.resolve()
    expect(ctx.onOutcome).not.toHaveBeenCalled()
    hooks.onFeedback('thumbs_up')
    hooks.onDismissed('dismissed')
    expect(ctx.onOutcome.mock.calls.map((call) => call[1].action)).toEqual([
      'thumbs_up',
      'dismissed'
    ])
  })
  it('rechecks expiry when the renderer acknowledges a queued item', () => {
    const ctx = context()
    const deadline = Date.now() + 100
    presentProactivityNotification(item, { ...ctx, expiresAt: deadline })
    vi.spyOn(Date, 'now').mockReturnValue(deadline + 1)
    state.notify.mock.calls[0][2].deliveryHooks.onPresented()
    expect(ctx.onOutcome).not.toHaveBeenCalled()
    vi.restoreAllMocks()
  })
  it('separates owner and outcome identities while retries remain stable', () => {
    const id = proactivityEventID('a', 'item', 'shown')
    expect(id).toBe(proactivityEventID('a', 'item', 'shown'))
    expect(id).not.toBe(proactivityEventID('b', 'item', 'shown'))
    expect(id).not.toBe(proactivityEventID('a', 'item', 'opened'))
  })
})
