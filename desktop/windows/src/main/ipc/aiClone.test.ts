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

// vi.hoisted: safely usable inside the vi.mock factory below despite vitest
// hoisting vi.mock calls above normal top-level statements (a plain `const`
// here would risk the same TDZ trap covered in beeperTokenStore.test.ts /
// aiClone.ts's own history — see the lazy-singleton comment in aiClone.ts).
const { mockCreateBeeperClient, mockBeeperClient } = vi.hoisted(() => {
  const mockBeeperClient = {
    verifyConnection: vi.fn(),
    listChats: vi.fn(),
    listRecentMessages: vi.fn(),
    sendMessage: vi.fn()
  }
  return { mockCreateBeeperClient: vi.fn(() => mockBeeperClient), mockBeeperClient }
})

vi.mock('../aiClone/beeperClient', () => ({
  createBeeperClient: mockCreateBeeperClient
}))

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

import {
  registerAiCloneHandlers,
  pollAiCloneChats,
  clearAiCloneUserData,
  __getSessionGenerationForTests
} from './aiClone'
import { ChatSettingsStore } from '../aiClone/chatSettingsStore'
import { DraftStore } from '../aiClone/draftStore'
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
  mockBeeperClient.verifyConnection.mockReset().mockResolvedValue([])
  mockBeeperClient.listChats.mockReset().mockResolvedValue([])
  mockBeeperClient.listRecentMessages.mockReset().mockResolvedValue([])
  mockBeeperClient.sendMessage.mockReset().mockResolvedValue(undefined)
  registerAiCloneHandlers()
})

/** Connects via the real aiClone:connect handler so approveDraft/submitDraft's
 *  send path (clientOrNull() → the cached client) has something to send
 *  through, exercising the actual wiring rather than reaching into internals. */
async function connect(): Promise<void> {
  mockBeeperClient.verifyConnection.mockResolvedValue([
    { accountID: 'a1', network: 'WhatsApp', displayName: 'Me' }
  ])
  await call('aiClone:connect', 'fake-token')
}

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
      sessionGeneration: __getSessionGenerationForTests(),
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
      sessionGeneration: __getSessionGenerationForTests(),
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
      sessionGeneration: __getSessionGenerationForTests(),
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
      sessionGeneration: __getSessionGenerationForTests(),
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

  it('does not advance the cursor for a new message until submitDraft confirms it was processed', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    const messageID = `msg-${Math.random().toString(36).slice(2)}`
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'draft' })
    settings.setCursor(chatID, 1000)

    const client = fakeClient({
      listRecentMessages: vi.fn().mockResolvedValue([
        {
          id: messageID,
          isSender: false,
          timestamp: 2000,
          text: 'are we on for 6?',
          senderID: 'u1'
        }
      ])
    })

    await pollAiCloneChats(client)
    expect(sentEvents).toHaveLength(1)
    // The message was broadcast, but nothing has confirmed it was actually
    // handled yet — the cursor must still be at its pre-poll value, not the
    // new message's timestamp.
    expect(settings.get(chatID)?.lastSeenTimestamp).toBe(1000)

    const event = sentEvents[0]?.payload as {
      messageID: string
      messageTimestamp: number
      sessionGeneration: number
    }
    await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'are we on for 6?',
      draftText: '',
      messageID: event.messageID,
      messageTimestamp: event.messageTimestamp,
      sessionGeneration: event.sessionGeneration
    })
    expect(settings.get(chatID)?.lastSeenTimestamp).toBe(2000)
  })

  it('drafts both siblings sharing one timestamp, and neither gets lost nor re-drafted', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    const idA = `msg-${Math.random().toString(36).slice(2)}`
    const idB = `msg-${Math.random().toString(36).slice(2)}`
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'draft' })
    settings.setCursor(chatID, 1000)

    const siblings = [
      { id: idA, isSender: false, timestamp: 2000, text: 'first', senderID: 'u1' },
      { id: idB, isSender: false, timestamp: 2000, text: 'second', senderID: 'u1' }
    ]
    const client = fakeClient({ listRecentMessages: vi.fn().mockResolvedValue(siblings) })

    await pollAiCloneChats(client)
    expect(sentEvents).toHaveLength(2)
    const generation = (sentEvents[0]?.payload as { sessionGeneration: number }).sessionGeneration

    // Resolve sibling A first. If cursor advancement naively overwrote the
    // tie-break set instead of accumulating into it, this would make B look
    // "already seen" on the very next poll before it's even been processed.
    await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'first',
      draftText: '',
      messageID: idA,
      messageTimestamp: 2000,
      sessionGeneration: generation
    })
    expect(settings.get(chatID)?.lastSeenMessageIds).toEqual([idA])

    // A poll right now must not re-broadcast A (in-flight/seen) or drop B
    // (still legitimately unresolved).
    sentEvents.length = 0
    await pollAiCloneChats(client)
    expect(sentEvents.map((e) => (e.payload as { messageID: string }).messageID)).toEqual([])

    await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'second',
      draftText: '',
      messageID: idB,
      messageTimestamp: 2000,
      sessionGeneration: generation
    })
    expect(settings.get(chatID)?.lastSeenMessageIds?.sort()).toEqual([idA, idB].sort())

    // Now that both are resolved, re-polling the same two messages must not
    // resurrect either of them.
    sentEvents.length = 0
    await pollAiCloneChats(client)
    expect(sentEvents).toHaveLength(0)
  })

  it('does not re-broadcast a message that is still in flight on the next poll tick', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    const messageID = `msg-${Math.random().toString(36).slice(2)}`
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'draft' })
    settings.setCursor(chatID, 1000)

    const client = fakeClient({
      listRecentMessages: vi
        .fn()
        .mockResolvedValue([
          { id: messageID, isSender: false, timestamp: 2000, text: 'hey', senderID: 'u1' }
        ])
    })

    await pollAiCloneChats(client)
    expect(sentEvents).toHaveLength(1)

    // Poll again without ever calling submitDraft for m1 — it's still
    // "in flight" from the renderer's perspective, so it must not be
    // rebroadcast a second time.
    await pollAiCloneChats(client)
    expect(sentEvents).toHaveLength(1)
  })

  it('guards against two overlapping poll runs for the same tick', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    const settings = new ChatSettingsStore()
    settings.upsert({ chatID, displayName: 'Jordan', mode: 'draft' })

    let resolveFetch: (() => void) | undefined
    const listRecentMessages = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = () => resolve([])
        })
    )
    const client = fakeClient({ listRecentMessages })

    const firstRun = pollAiCloneChats(client)
    const secondRun = pollAiCloneChats(client) // fires while the first is still awaiting the fetch
    resolveFetch?.()
    await Promise.all([firstRun, secondRun])

    // The second call should have returned immediately (pollInProgress
    // guard) without ever calling listRecentMessages itself.
    expect(listRecentMessages).toHaveBeenCalledTimes(1)
  })
})

describe('aiClone:setChatMode', () => {
  it('fails closed to off for an unrecognized mode value instead of persisting it verbatim', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    // Cast past the type system the same way a stale renderer build or a
    // malformed IPC call would arrive at runtime.
    await call('aiClone:setChatMode', chatID, 'Jordan', 'AUTO_SEND' as unknown)
    expect(new ChatSettingsStore().get(chatID)?.mode).toBe('off')
  })

  it('accepts a genuinely valid mode unchanged', async () => {
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    await call('aiClone:setChatMode', chatID, 'Jordan', 'auto_send')
    expect(new ChatSettingsStore().get(chatID)?.mode).toBe('auto_send')
  })
})

describe('idempotency', () => {
  it('submitDraft never sends the same message twice even under a concurrent duplicate call', async () => {
    await connect()
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    new ChatSettingsStore().upsert({ chatID, displayName: 'Jordan', mode: 'auto_send' })

    const args = {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'still on for 6?',
      draftText: 'yep!',
      messageID: 'dup-msg',
      messageTimestamp: 5000,
      sessionGeneration: __getSessionGenerationForTests()
    }

    const [first, second] = await Promise.all([
      call('aiClone:submitDraft', args),
      call('aiClone:submitDraft', args)
    ])

    expect(mockBeeperClient.sendMessage).toHaveBeenCalledTimes(1)
    // Exactly one of the two calls actually sent; the other saw the
    // in-progress guard and no-op'd.
    const actions = [first, second].map((r) => (r as { action: string }).action)
    expect(actions.filter((a) => a === 'sent')).toHaveLength(1)
    expect(actions.filter((a) => a === 'skipped')).toHaveLength(1)
  })

  it('approveDraft never sends the same draft twice even under a concurrent duplicate call', async () => {
    await connect()
    const draft = new DraftStore().add({
      sessionGeneration: __getSessionGenerationForTests(),
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'are we on for 6?',
      draftText: 'yep, see you then!'
    })

    await Promise.all([
      call('aiClone:approveDraft', draft.id),
      call('aiClone:approveDraft', draft.id)
    ])

    expect(mockBeeperClient.sendMessage).toHaveBeenCalledTimes(1)
    expect(new DraftStore().get(draft.id)).toBeNull()
  })

  it('re-queues a draft if the send itself fails, instead of losing it silently', async () => {
    await connect()
    mockBeeperClient.sendMessage.mockRejectedValueOnce(new Error('network down'))
    const draft = new DraftStore().add({
      sessionGeneration: __getSessionGenerationForTests(),
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'are we on for 6?',
      draftText: 'yep, see you then!'
    })

    await expect(call('aiClone:approveDraft', draft.id)).rejects.toThrow('network down')

    const remaining = new DraftStore().list()
    expect(remaining).toHaveLength(1)
    expect(remaining[0]?.draftText).toBe('yep, see you then!')
  })
})

describe('clearAiCloneUserData', () => {
  it('clears the token, chat settings, and drafts, and stops polling', async () => {
    await connect()
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    new ChatSettingsStore().upsert({ chatID, displayName: 'Jordan', mode: 'auto_send' })
    new DraftStore().add({
      sessionGeneration: __getSessionGenerationForTests(),
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'hi',
      draftText: 'hey!'
    })
    expect(new BeeperTokenStore().has()).toBe(true)

    clearAiCloneUserData()

    expect(new BeeperTokenStore().has()).toBe(false)
    expect(new ChatSettingsStore().list()).toEqual([])
    expect(new DraftStore().list()).toEqual([])
    // Status should now report disconnected since the token and cached
    // client are both gone.
    await expect(call('aiClone:status')).resolves.toEqual({ connected: false, accounts: [] })
  })
})

describe('session generation guard', () => {
  it('submitDraft refuses to send a message broadcast before a disconnect happened', async () => {
    await connect()
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    new ChatSettingsStore().upsert({ chatID, displayName: 'Jordan', mode: 'auto_send' })
    // Simulates the renderer's LLM call taking long enough that the user
    // disconnects Beeper before it finishes — this event was broadcast
    // under the connection that existed a moment ago, not the one live now.
    const staleGeneration = __getSessionGenerationForTests()

    await call('aiClone:disconnect')

    const result = await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'still on for 6?',
      draftText: 'yep!',
      messageID: 'msg-stale',
      messageTimestamp: 9000,
      sessionGeneration: staleGeneration
    })

    expect(result).toEqual({ action: 'skipped' })
    expect(mockBeeperClient.sendMessage).not.toHaveBeenCalled()
  })

  it('submitDraft refuses to send after reconnecting to a different account mid-draft', async () => {
    await connect()
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    new ChatSettingsStore().upsert({ chatID, displayName: 'Jordan', mode: 'auto_send' })
    const staleGeneration = __getSessionGenerationForTests()

    // Reconnect — a different (or the same) Beeper account, doesn't matter
    // which: any connect() bumps the generation, since chatID is only
    // meaningful within the connection it was fetched under.
    await connect()

    const result = await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'still on for 6?',
      draftText: 'yep!',
      messageID: 'msg-stale-2',
      messageTimestamp: 9500,
      sessionGeneration: staleGeneration
    })

    expect(result).toEqual({ action: 'skipped' })
    expect(mockBeeperClient.sendMessage).not.toHaveBeenCalled()
  })

  it('approveDraft discards (does not send) a queued draft from a generation that is no longer current', async () => {
    await connect()
    const staleGeneration = __getSessionGenerationForTests()
    const draft = new DraftStore().add({
      chatID: 'chat-1',
      chatDisplayName: 'Jordan',
      incomingMessageText: 'are we on for 6?',
      draftText: 'yep, see you then!',
      sessionGeneration: staleGeneration
    })

    // The account changed after this draft was queued for review.
    await connect()

    await call('aiClone:approveDraft', draft.id)

    expect(mockBeeperClient.sendMessage).not.toHaveBeenCalled()
    // Discarded, not silently left in the queue or re-added.
    expect(new DraftStore().get(draft.id)).toBeNull()
  })

  it('submitDraft still sends normally when the generation has not changed', async () => {
    await connect()
    const chatID = `chat-${Math.random().toString(36).slice(2)}`
    new ChatSettingsStore().upsert({ chatID, displayName: 'Jordan', mode: 'auto_send' })

    const result = await call('aiClone:submitDraft', {
      chatID,
      chatDisplayName: 'Jordan',
      incomingMessageText: 'still on for 6?',
      draftText: 'yep!',
      messageID: 'msg-fresh',
      messageTimestamp: 9999,
      sessionGeneration: __getSessionGenerationForTests()
    })

    expect(result).toEqual({ action: 'sent' })
    expect(mockBeeperClient.sendMessage).toHaveBeenCalledWith(chatID, 'yep!')
  })
})
