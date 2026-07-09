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

const firebaseMock = vi.hoisted(() => ({
  auth: {
    currentUser: null as null | { getIdToken: () => Promise<string> }
  }
}))

vi.mock('axios', () => ({
  default: {
    create: axiosMock.create
  }
}))

vi.mock('./firebase', () => firebaseMock)

import { fetchFirebaseIdToken } from './apiClient'

describe('fetchFirebaseIdToken', () => {
  it('rejects when no user is signed in', async () => {
    firebaseMock.auth.currentUser = null

    await expect(fetchFirebaseIdToken()).rejects.toThrow(
      'Sign in to Omi before generating an MCP key.'
    )
  })

  it('returns the current user token for main-process MCP key creation', async () => {
    firebaseMock.auth.currentUser = { getIdToken: vi.fn().mockResolvedValue('firebase-token') }

    await expect(fetchFirebaseIdToken()).resolves.toBe('firebase-token')
  })
})
