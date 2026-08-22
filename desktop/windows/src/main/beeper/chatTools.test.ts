import { describe, it, expect, vi } from 'vitest'
import { BeeperHttpError, type BeeperAccountRow, type BeeperChat } from './client'
import {
  connectedNetworkLabels,
  createDraftBeeperReplyExecutor,
  createGetBeeperMessagesExecutor,
  createSearchBeeperChatsExecutor,
  formatBeeperChats,
  formatBeeperMessages,
  matchBeeperAccounts,
  type BeeperChatToolDeps,
  type BeeperDraftToolDeps
} from './chatTools'

const ctx = (signal?: AbortSignal) => ({
  sessionId: 's1',
  adapterId: 'pi-mono',
  signal: signal ?? new AbortController().signal
})

const linkedin: BeeperAccountRow = {
  accountID: 'local-linkedin_1',
  network: 'LinkedIn',
  status: 'connected',
  bridge: { type: 'linkedin' }
}

const telegram: BeeperAccountRow = {
  accountID: 'local-telegram_1',
  network: 'Telegram',
  status: 'connected',
  bridge: { type: 'telegram' }
}

function deps(partial: Partial<BeeperChatToolDeps> = {}): BeeperChatToolDeps {
  return {
    probe: async () => ({ running: true }),
    loadToken: async () => 'tok',
    listAccounts: async () => [linkedin, telegram],
    searchChats: async () => [],
    listMessages: async () => [],
    ...partial
  }
}

describe('matchBeeperAccounts', () => {
  it('matches display name, account id, and bridge type', () => {
    expect(matchBeeperAccounts([linkedin, telegram], 'linkedin').map((a) => a.accountID)).toEqual([
      'local-linkedin_1'
    ])
    expect(matchBeeperAccounts([linkedin], 'local-linkedin').map((a) => a.network)).toEqual([
      'LinkedIn'
    ])
  })
})

describe('formatBeeperChats / formatBeeperMessages', () => {
  it('renders chat_id so the model can call get_beeper_messages', () => {
    const chats: BeeperChat[] = [
      {
        id: '!li_1',
        network: 'LinkedIn',
        type: 'single',
        title: 'Alex',
        unreadCount: 2,
        lastActivity: '2026-08-18T22:59:00.000Z',
        preview: { id: 'm1', text: 'hey, got a minute?' }
      }
    ]
    const out = formatBeeperChats(chats)
    expect(out).toContain('chat_id: !li_1')
    expect(out).toContain('unread 2')
    expect(out).toContain('get_beeper_messages')
    expect(out).toContain('draft_beeper_reply')
  })

  it('labels the user as You and skips deleted rows', () => {
    const out = formatBeeperMessages('!li_1', [
      { id: '1', text: 'hi', senderName: 'Alex', timestamp: '2026-08-18T12:00:00.000Z' },
      { id: '2', text: 'gone', isDeleted: true },
      { id: '3', text: 'on my way', isSender: true, timestamp: '2026-08-18T12:01:00.000Z' }
    ])
    expect(out).toContain('Alex: hi')
    expect(out).toContain('You: on my way')
    expect(out).not.toContain('gone')
  })

  it('lists connected network labels', () => {
    expect(connectedNetworkLabels([linkedin, telegram])).toBe('LinkedIn, Telegram')
  })
})

describe('search_beeper_chats', () => {
  it('asks the user to open Beeper when Desktop is down', async () => {
    const exec = createSearchBeeperChatsExecutor(deps({ probe: async () => ({ running: false }) }))
    expect(await exec({}, ctx())).toContain('not running')
  })

  it('asks to paste a token when Omi has none', async () => {
    const exec = createSearchBeeperChatsExecutor(deps({ loadToken: async () => null }))
    expect(await exec({}, ctx())).toContain('not connected')
  })

  it('filters by network via accountIDs', async () => {
    const searchChats = vi.fn(async () => [
      {
        id: '!li_1',
        network: 'LinkedIn',
        type: 'single',
        title: 'Alex',
        unreadCount: 0
      } satisfies BeeperChat
    ])
    const exec = createSearchBeeperChatsExecutor(deps({ searchChats }))
    const out = await exec({ network: 'linkedin' }, ctx())
    expect(searchChats).toHaveBeenCalledWith(
      'tok',
      expect.objectContaining({ accountIDs: ['local-linkedin_1'] })
    )
    expect(out).toContain('Alex')
    expect(out).toContain('chat_id: !li_1')
  })

  it('errors with connected networks when the filter misses', async () => {
    const exec = createSearchBeeperChatsExecutor(deps())
    const out = await exec({ network: 'whatsapp' }, ctx())
    expect(out).toContain('matching "whatsapp"')
    expect(out).toContain('LinkedIn, Telegram')
  })

  it('maps a 401 to a token-refresh hint', async () => {
    const exec = createSearchBeeperChatsExecutor(
      deps({
        searchChats: async () => {
          throw new BeeperHttpError(401, 'nope')
        }
      })
    )
    expect(await exec({}, ctx())).toContain('rejected the token')
  })
})

describe('get_beeper_messages', () => {
  it('requires chat_id', async () => {
    const exec = createGetBeeperMessagesExecutor(deps())
    expect(await exec({}, ctx())).toContain('chat_id is required')
  })

  it('returns formatted messages for a chat', async () => {
    const exec = createGetBeeperMessagesExecutor(
      deps({
        listMessages: async () => [
          { id: '1', text: 'flight is 6:40', senderName: 'Alex', timestamp: '2026-08-18T12:00:00Z' }
        ]
      })
    )
    const out = await exec({ chat_id: '!li_1' }, ctx())
    expect(out).toContain('Alex: flight is 6:40')
  })
})

describe('draft_beeper_reply', () => {
  function draftDeps(partial: Partial<BeeperDraftToolDeps> = {}): BeeperDraftToolDeps {
    return {
      ...deps(),
      getChat: async () => ({
        id: '!li_1',
        network: 'LinkedIn',
        type: 'single',
        title: 'Alex',
        unreadCount: 1
      }),
      generateReply: async () => 'Landing at 6:40 — I will text when I am through baggage.',
      presentDraft: (draft) => draft,
      newId: () => 'draft-1',
      now: () => 1_700_000_000_000,
      ...partial
    }
  }

  it('requires chat_id', async () => {
    const exec = createDraftBeeperReplyExecutor(draftDeps())
    expect(await exec({}, ctx())).toContain('chat_id is required')
  })

  it('errors when the thread has no inbound message', async () => {
    const exec = createDraftBeeperReplyExecutor(
      draftDeps({
        listMessages: async () => [{ id: '1', text: 'already replied', isSender: true }]
      })
    )
    expect(await exec({ chat_id: '!li_1' }, ctx())).toContain('No inbound message')
  })

  it('presents a Send/Skip draft and tells the model not to send', async () => {
    const presented: unknown[] = []
    const exec = createDraftBeeperReplyExecutor(
      draftDeps({
        listMessages: async () => [
          {
            id: 'm1',
            text: 'hey what time does your flight land tomorrow?',
            senderName: 'Alex',
            timestamp: '2026-08-18T12:00:00Z'
          }
        ],
        presentDraft: (draft) => {
          presented.push(draft)
          return draft
        }
      })
    )
    const out = await exec({ chat_id: '!li_1' }, ctx())
    expect(presented).toHaveLength(1)
    expect(presented[0]).toMatchObject({
      id: 'draft-1',
      chatId: '!li_1',
      chatTitle: 'Alex',
      network: 'LinkedIn',
      inboundText: 'hey what time does your flight land tomorrow?'
    })
    expect(out).toContain('Send/Skip card is on screen')
    expect(out).toContain('Never send it yourself')
    expect(out).toContain('Landing at 6:40')
  })

  it('maps a Beeper 401 to a token-refresh hint', async () => {
    const exec = createDraftBeeperReplyExecutor(
      draftDeps({
        listMessages: async () => {
          throw new BeeperHttpError(401, 'nope')
        }
      })
    )
    expect(await exec({ chat_id: '!li_1' }, ctx())).toContain('rejected the token')
  })
})
