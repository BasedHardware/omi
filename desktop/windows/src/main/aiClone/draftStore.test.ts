import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'draft-store-test-'))

vi.mock('electron', () => ({
  app: { getPath: (): string => dir }
}))

import { DraftStore } from './draftStore'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

let store: DraftStore

beforeEach(() => {
  store = new DraftStore(join(dir, `drafts-${Math.random().toString(36).slice(2)}.json`))
})

describe('DraftStore', () => {
  it('starts empty', () => {
    expect(store.list()).toEqual([])
  })

  it('add assigns an id and createdAt, and the draft round-trips', () => {
    const added = store.add({
      sessionGeneration: 0,
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'are we still on for 6?',
      draftText: 'yep, see you then!'
    })
    expect(added.id).toBeTruthy()
    expect(added.createdAt).toBeGreaterThan(0)
    expect(store.get(added.id)).toEqual(added)
    expect(store.list()).toEqual([added])
  })

  it('remove deletes only the targeted draft', () => {
    const a = store.add({
      sessionGeneration: 0,
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'a',
      draftText: 'a reply'
    })
    const b = store.add({
      sessionGeneration: 0,
      chatID: 'chat-2',
      chatDisplayName: 'Sam',
      incomingMessageText: 'b',
      draftText: 'b reply'
    })
    store.remove(a.id)
    expect(store.get(a.id)).toBeNull()
    expect(store.get(b.id)).toEqual(b)
  })

  it('get returns null for an unknown id', () => {
    expect(store.get('nope')).toBeNull()
  })

  it('take returns and removes the draft in one call', () => {
    const added = store.add({
      sessionGeneration: 0,
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'are we still on for 6?',
      draftText: 'yep, see you then!'
    })
    expect(store.take(added.id)).toEqual(added)
    // A second take (simulating a double-click / overlapping approve call)
    // must see it already gone — this is the idempotency guarantee.
    expect(store.take(added.id)).toBeNull()
    expect(store.get(added.id)).toBeNull()
  })

  it('take returns null for an unknown id without touching other drafts', () => {
    const kept = store.add({
      sessionGeneration: 0,
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'a',
      draftText: 'a reply'
    })
    expect(store.take('nope')).toBeNull()
    expect(store.get(kept.id)).toEqual(kept)
  })

  it('clearAll removes every queued draft', () => {
    store.add({
      sessionGeneration: 0,
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'a',
      draftText: 'a reply'
    })
    store.add({
      sessionGeneration: 0,
      chatID: 'chat-2',
      chatDisplayName: 'Sam',
      incomingMessageText: 'b',
      draftText: 'b reply'
    })
    store.clearAll()
    expect(store.list()).toEqual([])
  })
})
