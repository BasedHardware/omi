import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync, existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import type { BeeperClient } from '../aiClone/beeperClient'

const dir = mkdtempSync(join(tmpdir(), 'ai-clone-ipc-test-'))

type Handler = (event: unknown, ...args: unknown[]) => unknown
type SendFn = (channel: string, payload: unknown) => void
const handlers = new Map<string, Handler>()
const sentEvents: Array<{ channel: string; payload: unknown }> = []

vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  safeStorage: {
    isEncryptionAvailable: (): boolean => true,
    encryptString: (s: string): Buffer => Buffer.from(s, 'utf8'),
    decryptString: (b: Buffer): string => b.toString('utf8')
  },
  ipcMain: {
    handle: (channel: string, fn: Handler): void => {
      handlers.set(channel, fn)
    }
  },
  BrowserWindow: {
    getAllWindows: (): Array<{ isDestroyed: () => boolean; webContents: { send: SendFn } }> => [
      {
        isDestroyed: () => false,
        webContents: {
          send: (channel, payload) => {
            sentEvents.push({ channel, payload })
          }
        }
      }
    ]
  }
}))

vi.mock('../assistants/aiUserProfile/service', () => ({
  getLatestProfileText: (): string | null => null
}))

import { registerAiCloneHandlers, pollAiCloneChats } from './aiClone'
import { ChatSettingsStore } from '../aiClone/chatSettingsStore'
import { BeeperTokenStore } from '../aiClone/beeperTokenStore'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

function call(channel: string, ...args: unknown[]): unknown {
  const fn = handlers.get(channel)
  if (!fn) throw new Error(`no handler registered for ${channel}`)
  return fn({}, ...args)
}

function fakeClient(overrides: Partial<BeeperClient> = {}): BeeperClient {
  return {
    verifyConnection: vi.fn().mockResolvedValue([]),
    listChats: vi.fn().mockResolvedValue([]),
    listRecentMessages: vi.fn().mockResolvedValue([]),
    sendMessage: vi.fn().mockResolvedValue(undefined),
    ...overrides
  }
}

beforeEach(() => {
  handlers.clear()
  sentEvents.length = 0
  // aiClone.ts's stores use fixed default filenames under userData (here, our
  // temp `dir`) rather than a per-instance path — fine in the real app (one
  // process, one store), but it means every test in this file shares the same
  // underlying files unless we reset them here.
  new BeeperTokenStore().clear()
  for (const path of ['ai-clone-chat-settings.json', 'ai-clone-drafts.json']) {
    const full = join(dir, path)
    if (existsSync(full)) rmSync(full, { force: true })
  }
  registerAiCloneHandlers()
})

describe('registerAiCloneHandlers', () => {
  it('registers every AI-clone channel', () => {
    expect([...handlers.keys()].sort()).toEqual(
      [
        'aiClone:connect',
        'aiClone:status',
        'aiClone:disconnect',
        'aiClone:listChats',
        'aiClone:setChatMode',
        'aiClone:listDrafts',
        'aiClone:approveDraft',
        'aiClone:dismissDraft',
        'aiClone:submitDraft'
      ].sort()
    )
  })

  it('status is disconnected with no accounts before anything is connected', async () => {
    await expect(call('aiClone:status')).resolves.toEqual({ connected: false, accounts: [] })
  })

  it('listChats returns empty before a token is connected', async () => {
    await expect(call('aiClone:listChats')).resolves.toEqual([])
  })
})

describe('aiClone:submitDraft', () => {
  const chatID = `chat-${Math.random().toString(36).slice(2)}`

  it('skips when the chat mode is off (or unset)', async () => {
    const result = await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'hey',
      draftText: 'sounds good!'
    })
    expect(result).toEqual({ action: 'skipped' })
  })

  it('queues for review in draft mode', async () => {
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'draft' })
    const result = (await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'hey',
      draftText: 'sounds good!'
    })) as { action: string; draft?: { draftText: string } }
    expect(result.action).toBe('queued_for_review')
    expect(result.draft?.draftText).toBe('sounds good!')
  })

  it('queues a [NEEDS_INPUT] draft for review even in auto_send mode', async () => {
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'auto_send' })
    const result = (await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'what time works?',
      draftText: '[NEEDS_INPUT] not sure what time the user meant'
    })) as { action: string }
    expect(result.action).toBe('queued_for_review')
  })

  it('queues a sensitive-topic draft for review even in auto_send mode', async () => {
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'auto_send' })
    const result = (await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'can you wire me the deposit?',
      draftText: 'sure, what is your bank account and routing number?'
    })) as { action: string }
    expect(result.action).toBe('queued_for_review')
  })
})

describe('pollAiCloneChats', () => {
  it('broadcasts an incomingMessage event for a new inbound message on an opted-in chat', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'draft' })
    // First poll establishes the cursor and drafts nothing retroactively
    // (chatMonitor's documented first-poll behavior) — seed a cursor so this
    // test's "new" message is unambiguous.
    settings.setCursor(chatID, 1000)

    const client = fakeClient({
      listRecentMessages: vi.fn().mockResolvedValue([
        {
          id: 'm1',
          isSender: false,
          timestamp: 2000,
          text: 'are we still on for 6?',
          senderID: 'u1'
        }
      ])
    })

    await pollAiCloneChats(client)

    expect(sentEvents).toHaveLength(1)
    expect(sentEvents[0]?.channel).toBe('aiClone:incomingMessage')
    expect(sentEvents[0]?.payload).toMatchObject({
      chatID,
      chatDisplayName: 'Jordan',
      mode: 'draft',
      incomingMessageText: 'are we still on for 6?'
    })
  })

  it('does not re-broadcast a message already covered by the cursor', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'draft' })
    settings.setCursor(chatID, 5000)

    const client = fakeClient({
      listRecentMessages: vi
        .fn()
        .mockResolvedValue([
          { id: 'old', isSender: false, timestamp: 1000, text: 'hi', senderID: 'u1' }
        ])
    })

    await pollAiCloneChats(client)
    expect(sentEvents).toHaveLength(0)
  })

  it('skips chats with mode off', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'off' })

    const client = fakeClient()
    await pollAiCloneChats(client)
    expect(client.listRecentMessages).not.toHaveBeenCalled()
  })
})
