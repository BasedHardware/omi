import { it, expect, vi } from 'vitest'
import {
  addPendingConversation,
  clearPendingConversations,
  refreshCloudConversations,
  subscribeCloudRefresh
} from './pageCache'

it('gives pending conversations distinct ids created in the same millisecond', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-19T00:00:00Z'))

  const first = addPendingConversation('first')
  const second = addPendingConversation('second')
  const [firstKind, firstTimestamp, firstSequence] = first.split('-')
  const [secondKind, secondTimestamp, secondSequence] = second.split('-')

  expect(first).not.toBe(second)
  expect([firstKind, firstTimestamp]).toEqual([secondKind, secondTimestamp])
  expect(firstKind).toBe('pending')
  expect(firstSequence).not.toBe(secondSequence)

  clearPendingConversations()
  vi.useRealTimers()
})

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
