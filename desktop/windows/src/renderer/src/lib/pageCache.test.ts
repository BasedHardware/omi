import { it, expect, vi } from 'vitest'
import { refreshCloudConversations, subscribeCloudRefresh } from './pageCache'

it('refreshCloudConversations coalesces rapid calls into one debounced notify', () => {
  vi.useFakeTimers()
  let calls = 0
  const unsub = subscribeCloudRefresh(() => {
    calls++
  })
  refreshCloudConversations()
  refreshCloudConversations()
  vi.advanceTimersByTime(500)
  expect(calls).toBe(1) // two rapid calls coalesced into one
  unsub()
  refreshCloudConversations()
  vi.advanceTimersByTime(500)
  expect(calls).toBe(1) // no notify after unsubscribe
  vi.useRealTimers()
})
