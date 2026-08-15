import { describe, expect, it } from 'vitest'
import { isConversationsPanelActive } from './conversationsPanelActivity'

describe('isConversationsPanelActive', () => {
  it.each(['/home', '/tasks', '/settings', '/conversations/abc123', '/conversations/live'])(
    'returns false for inactive route %s',
    (pathname) => {
      expect(isConversationsPanelActive(pathname)).toBe(false)
    }
  )

  it('returns true only for the conversations panel route', () => {
    expect(isConversationsPanelActive('/conversations')).toBe(true)
  })
})
