import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'chat-settings-store-test-'))

vi.mock('electron', () => ({
  app: { getPath: (): string => dir }
}))

import { ChatSettingsStore } from './chatSettingsStore'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

let store: ChatSettingsStore
let filePath: string

beforeEach(() => {
  filePath = join(dir, `settings-${Math.random().toString(36).slice(2)}.json`)
  store = new ChatSettingsStore(filePath)
})

describe('ChatSettingsStore', () => {
  it('returns null/empty when nothing is stored', () => {
    expect(store.get('chat-1')).toBeNull()
    expect(store.list()).toEqual([])
  })

  it('upsert then get round-trips', () => {
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'draft' })
    expect(store.get('chat-1')).toEqual({
      chatID: 'chat-1',
      displayName: 'Jordan',
      mode: 'draft',
      lastSeenTimestamp: undefined
    })
  })

  it('setCursor advances an existing chat’s cursor without touching its mode', () => {
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'auto_send' })
    store.setCursor('chat-1', 12345)
    expect(store.get('chat-1')).toMatchObject({ mode: 'auto_send', lastSeenTimestamp: 12345 })
  })

  it('setCursor is a no-op for a chat that was never upserted', () => {
    store.setCursor('unknown', 999)
    expect(store.get('unknown')).toBeNull()
  })

  it('re-upserting a mode preserves the existing cursor (no retroactive burst on re-opt-in)', () => {
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'draft' })
    store.setCursor('chat-1', 500)
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'off' })
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'draft' })
    expect(store.get('chat-1')?.lastSeenTimestamp).toBe(500)
  })

  it('remove deletes a chat’s settings', () => {
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'draft' })
    store.remove('chat-1')
    expect(store.get('chat-1')).toBeNull()
  })

  it('list returns all stored chats', () => {
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'draft' })
    store.upsert({ chatID: 'chat-2', displayName: 'Sam', mode: 'off' })
    expect(
      store
        .list()
        .map((s) => s.chatID)
        .sort()
    ).toEqual(['chat-1', 'chat-2'])
  })

  it('coerces an unrecognized persisted mode to off (fail closed against a corrupted file)', () => {
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'auto_send' })
    // Simulate a hand-edited/corrupted file by writing an invalid mode
    // directly, bypassing upsert's normal typed path.
    const raw = JSON.parse(readFileSync(filePath, 'utf8'))
    raw['chat-1'].mode = 'AUTO_SEND'
    writeFileSync(filePath, JSON.stringify(raw))
    expect(store.get('chat-1')?.mode).toBe('off')
  })

  it('clearAll removes every stored chat setting', () => {
    store.upsert({ chatID: 'chat-1', displayName: 'Jordan', mode: 'draft' })
    store.upsert({ chatID: 'chat-2', displayName: 'Sam', mode: 'auto_send' })
    store.clearAll()
    expect(store.list()).toEqual([])
  })
})
