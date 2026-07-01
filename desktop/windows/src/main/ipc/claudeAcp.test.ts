import { describe, expect, it, vi } from 'vitest'

vi.mock('electron', () => ({
  ipcMain: {
    handle: vi.fn()
  }
}))

import { normalizeClaudeAcpRequest } from './claudeAcp'

describe('Claude ACP IPC normalization', () => {
  it('accepts well-formed chat messages', () => {
    expect(
      normalizeClaudeAcpRequest({
        messages: [
          { role: 'user', content: 'hello' },
          { role: 'assistant', content: 'hi' }
        ]
      })
    ).toEqual({
      messages: [
        { role: 'user', content: 'hello' },
        { role: 'assistant', content: 'hi' }
      ]
    })
  })

  it('rejects malformed message entries', () => {
    expect(() => normalizeClaudeAcpRequest({ messages: [null] })).toThrow(
      'Claude ACP message must be an object'
    )
    expect(() => normalizeClaudeAcpRequest({ messages: [{ role: 'tool', content: 'x' }] })).toThrow(
      'Claude ACP message role must be user or assistant'
    )
  })

  it('caps message count and content length', () => {
    expect(() =>
      normalizeClaudeAcpRequest({
        messages: Array.from({ length: 101 }, () => ({ role: 'user', content: 'x' }))
      })
    ).toThrow('at most 100 messages')

    expect(() =>
      normalizeClaudeAcpRequest({
        messages: [{ role: 'user', content: 'x'.repeat(20_001) }]
      })
    ).toThrow('exceeds 20000 characters')
  })
})
