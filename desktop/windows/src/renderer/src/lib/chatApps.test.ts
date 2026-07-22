import { describe, it, expect, vi } from 'vitest'
import { worksWithChat, listChatApps, type ChatAppsClientLike } from './chatApps'
import type { App } from './omiApi.generated'

// chatApps owns the "which apps qualify for the chat picker" rule (Mac
// worksWithChat: capability "chat" OR "persona") and the enabled-apps fetch.

describe('worksWithChat', () => {
  it('accepts an app with the "chat" capability', () => {
    expect(worksWithChat(['chat'])).toBe(true)
  })
  it('accepts an app with the "persona" capability', () => {
    expect(worksWithChat(['persona'])).toBe(true)
    expect(worksWithChat(['memories', 'persona'])).toBe(true)
  })
  it('rejects an app with neither capability', () => {
    expect(worksWithChat(['memories', 'external_integration'])).toBe(false)
  })
  it('treats undefined/null/empty capabilities as non-chat', () => {
    expect(worksWithChat(undefined)).toBe(false)
    expect(worksWithChat(null)).toBe(false)
    expect(worksWithChat([])).toBe(false)
  })
})

// Minimal App fixtures — only the fields listChatApps reads.
function app(over: Partial<App>): App {
  return {
    id: 'x',
    name: 'X',
    author: 'A',
    image: 'https://img/x.png',
    capabilities: [],
    category: 'c',
    description: 'd',
    enabled: false,
    ...over
  } as App
}

describe('listChatApps', () => {
  it('returns only ENABLED apps whose capabilities work with chat, projected to ChatApp', async () => {
    const rows: App[] = [
      app({ id: 'a', name: 'Persona A', enabled: true, capabilities: ['persona'] }),
      app({ id: 'b', name: 'Chat B', enabled: true, capabilities: ['chat'] }),
      // enabled but not a chat app → excluded
      app({ id: 'c', name: 'Memories C', enabled: true, capabilities: ['memories'] }),
      // chat-capable but NOT enabled → excluded
      app({ id: 'd', name: 'Disabled D', enabled: false, capabilities: ['chat'] })
    ]
    const client: ChatAppsClientLike = { get: vi.fn(async () => ({ data: rows })) }
    const result = await listChatApps(client)
    expect(result.map((a) => a.id)).toEqual(['a', 'b'])
    expect(result[0]).toEqual({
      id: 'a',
      name: 'Persona A',
      image: 'https://img/x.png',
      author: 'A'
    })
    // It hits the per-user apps endpoint.
    expect(client.get).toHaveBeenCalledWith('/v1/apps', { params: { include_reviews: false } })
  })

  it('resolves to [] (never throws) when the fetch fails', async () => {
    const client: ChatAppsClientLike = {
      get: vi.fn(async () => {
        throw new Error('network')
      })
    }
    await expect(listChatApps(client)).resolves.toEqual([])
  })

  it('tolerates a non-array payload', async () => {
    const client = { get: vi.fn(async () => ({ data: null })) } as unknown as ChatAppsClientLike
    await expect(listChatApps(client)).resolves.toEqual([])
  })
})
