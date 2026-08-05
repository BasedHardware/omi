import { describe, expect, it, vi } from 'vitest'

const accountsList = vi.fn()
const chatsSearch = vi.fn()
const messagesList = vi.fn()
const messagesSend = vi.fn()

function asyncIterable<T>(items: T[]): AsyncIterable<T> {
  return {
    [Symbol.asyncIterator]: async function* () {
      for (const item of items) yield item
    }
  }
}

vi.mock('@beeper/desktop-api', () => ({
  default: class FakeBeeperDesktop {
    accounts = { list: accountsList }
    chats = { search: chatsSearch }
    messages = { list: messagesList, send: messagesSend }
  }
}))

import { createBeeperClient } from './beeperClient'

describe('createBeeperClient', () => {
  it('verifyConnection maps accounts, falling back through display-name fields', async () => {
    accountsList.mockResolvedValue([
      { accountID: 'a1', network: 'WhatsApp', user: { fullName: 'Jordan Lee' } },
      { accountID: 'a2', network: 'Telegram', user: { username: 'sam_t' } },
      { accountID: 'a3', bridge: { type: 'imessage' }, user: {} }
    ])
    const client = createBeeperClient('token')
    await expect(client.verifyConnection()).resolves.toEqual([
      { accountID: 'a1', network: 'WhatsApp', displayName: 'Jordan Lee' },
      { accountID: 'a2', network: 'Telegram', displayName: 'sam_t' },
      { accountID: 'a3', network: 'imessage', displayName: 'a3' }
    ])
  })

  it('verifyConnection propagates a bad-token/API error to the caller', async () => {
    accountsList.mockRejectedValue(new Error('401 unauthorized'))
    const client = createBeeperClient('bad-token')
    await expect(client.verifyConnection()).rejects.toThrow('401 unauthorized')
  })

  it('listChats maps chats and stops at the requested limit', async () => {
    chatsSearch.mockResolvedValue(
      asyncIterable([
        { id: 'c1', title: 'Alex', network: 'WhatsApp', type: 'single', lastActivity: 't1' },
        { id: 'c2', title: 'Team', network: 'Telegram', type: 'group', lastActivity: 't2' },
        { id: 'c3', title: 'Extra', network: 'WhatsApp', type: 'single', lastActivity: 't3' }
      ])
    )
    const client = createBeeperClient('token')
    const chats = await client.listChats(2)
    expect(chats).toEqual([
      {
        chatID: 'c1',
        displayName: 'Alex',
        network: 'WhatsApp',
        type: 'single',
        lastActivity: 't1'
      },
      { chatID: 'c2', displayName: 'Team', network: 'Telegram', type: 'group', lastActivity: 't2' }
    ])
    expect(chatsSearch).toHaveBeenCalledWith({ type: 'any', limit: 2 })
  })

  it('listRecentMessages converts ISO timestamps to epoch ms', async () => {
    messagesList.mockResolvedValue(
      asyncIterable([
        {
          id: 'm1',
          isSender: false,
          timestamp: '2024-01-01T00:00:00.000Z',
          text: 'hey',
          senderID: 'u1'
        }
      ])
    )
    const client = createBeeperClient('token')
    const messages = await client.listRecentMessages('chat-1')
    expect(messages).toEqual([
      {
        id: 'm1',
        isSender: false,
        timestamp: Date.parse('2024-01-01T00:00:00.000Z'),
        text: 'hey',
        senderID: 'u1'
      }
    ])
    expect(messagesList).toHaveBeenCalledWith('chat-1')
  })

  it('sendMessage passes text through to the SDK', async () => {
    messagesSend.mockResolvedValue({ chatID: 'chat-1', pendingMessageID: 'p1' })
    const client = createBeeperClient('token')
    await client.sendMessage('chat-1', 'hello there')
    expect(messagesSend).toHaveBeenCalledWith('chat-1', { text: 'hello there' })
  })
})
