import { describe, expect, it } from 'vitest'
import { toConversationFolder } from './folders'
import type { Folder } from '../omiApi.generated'

function backendFolder(over: Partial<Folder> = {}): Folder {
  return {
    id: 'f1',
    name: 'Work',
    color: '#6B7280',
    icon: 'folder',
    order: 2,
    is_system: false,
    conversation_count: 5,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-05T00:00:00Z',
    ...over
  }
}

describe('toConversationFolder', () => {
  it('maps backend snake_case fields to the local cache shape', () => {
    expect(toConversationFolder(backendFolder())).toEqual({
      id: 'f1',
      name: 'Work',
      color: '#6B7280',
      icon: 'folder',
      orderIdx: 2,
      isSystem: false,
      conversationCount: 5,
      updatedAt: new Date('2026-01-05T00:00:00Z').getTime()
    })
  })

  it('defaults missing optional fields', () => {
    const f = toConversationFolder(
      backendFolder({
        color: undefined,
        icon: undefined,
        order: undefined,
        conversation_count: undefined
      })
    )
    expect(f).toMatchObject({ color: null, icon: null, orderIdx: 0, conversationCount: 0 })
  })

  it('marks system folders', () => {
    expect(toConversationFolder(backendFolder({ is_system: true })).isSystem).toBe(true)
  })
})
