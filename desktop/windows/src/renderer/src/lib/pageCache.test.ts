import { it, expect, vi } from 'vitest'
import {
  refreshCloudConversations,
  subscribeCloudRefresh,
  addPendingConversation,
  getPendingConversation,
  removePendingConversation
} from './pageCache'

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

it('keeps a pending row retrievable by id with its full transcript (detail renders without a cloud GET)', () => {
  const transcript = 'a'.repeat(500) // longer than the 200-char preview slice
  const id = addPendingConversation(transcript)
  expect(id.startsWith('pending-')).toBe(true)
  const row = getPendingConversation(id)
  expect(row).toBeDefined()
  expect(row?.pending).toBe(true)
  expect(row?.transcript).toBe(transcript) // full transcript, not the truncated preview
  expect(row?.preview.length).toBe(200)
})

it('returns undefined for an unknown pending id (so the detail view can show a notice, not 404)', () => {
  expect(getPendingConversation('pending-does-not-exist')).toBeUndefined()
})

it('removePendingConversation drops a pending row so a list delete sticks (no cloud 404 / reappear)', () => {
  const id = addPendingConversation('some transcript')
  expect(getPendingConversation(id)).toBeDefined()
  removePendingConversation(id)
  expect(getPendingConversation(id)).toBeUndefined()
  // Removing an unknown id is a harmless no-op.
  expect(() => removePendingConversation('pending-nope')).not.toThrow()
})
