import { describe, it, expect } from 'vitest'
import {
  isLocalConversationId,
  isPendingConversationId,
  isServerConversationId
} from './conversationId'

describe('conversation id classification', () => {
  it('classifies local recording and chat ids as local', () => {
    expect(isLocalConversationId('local-abc123')).toBe(true)
    expect(isLocalConversationId('chat-abc123')).toBe(true)
    expect(isLocalConversationId('pending-1-x')).toBe(false)
    expect(isLocalConversationId('srv_realid')).toBe(false)
  })

  it('classifies optimistic placeholder ids as pending', () => {
    expect(isPendingConversationId('pending-1700000000000-abc')).toBe(true)
    expect(isPendingConversationId('local-abc')).toBe(false)
    expect(isPendingConversationId('srv_realid')).toBe(false)
  })

  // Regression guard for the "request failed with status 404" bug: a client-minted
  // pending id must NEVER be treated as server-fetchable.
  it('never treats a pending id as a server-fetchable id', () => {
    expect(isServerConversationId('pending-1700000000000-abc')).toBe(false)
  })

  it('treats real server ids as server-fetchable and excludes local/empty ids', () => {
    expect(isServerConversationId('srv_realid')).toBe(true)
    expect(isServerConversationId('local-abc')).toBe(false)
    expect(isServerConversationId('chat-abc')).toBe(false)
    expect(isServerConversationId('')).toBe(false)
  })
})
