import { describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => {
  const post = vi.fn()
  const create = vi.fn(() => ({
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    },
    post
  }))
  return { create, post }
})

vi.mock('axios', () => ({
  default: {
    create: axiosMock.create
  }
}))

vi.mock('./firebase', () => ({
  auth: {
    currentUser: null
  }
}))

import { createWindowsMcpKey } from './apiClient'

describe('createWindowsMcpKey', () => {
  it('posts the Windows MCP key name and returns the key record', async () => {
    const record = { id: 'key_123', name: 'Omi Windows', key: 'omi_live_secret' }
    axiosMock.post.mockResolvedValueOnce({ data: record })

    await expect(createWindowsMcpKey()).resolves.toEqual(record)
    expect(axiosMock.post).toHaveBeenCalledWith('/v1/mcp/keys', { name: 'Omi Windows' })
  })
})
