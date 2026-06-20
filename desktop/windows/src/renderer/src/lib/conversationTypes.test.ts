import { it, expect } from 'vitest'
import { classifyConversationId } from './conversationTypes'

it('classifies pending optimistic placeholders as pending (no cloud GET → no 404)', () => {
  expect(classifyConversationId('pending-1716000000000-abc123')).toBe('pending')
})

it('classifies local recordings and saved chats as local', () => {
  expect(classifyConversationId('local-3f2a-uuid')).toBe('local')
  expect(classifyConversationId('chat-9981')).toBe('local')
})

it('classifies real backend ids as cloud', () => {
  expect(classifyConversationId('65f0c1e2a4b9d8')).toBe('cloud')
  // A cloud id that merely contains (but does not start with) a reserved prefix
  // is still cloud.
  expect(classifyConversationId('abc-local-def')).toBe('cloud')
})
