import { describe, it, expect, vi, beforeEach } from 'vitest'

const { omiPost } = vi.hoisted(() => ({ omiPost: vi.fn() }))
vi.mock('./apiClient', () => ({
  omiApi: { post: omiPost }
}))

import { generateConversationTopic } from './conversationTopic'

beforeEach(() => {
  omiPost.mockReset()
})

describe('generateConversationTopic', () => {
  it('reads emoji and title from the backend topic SSOT', async () => {
    omiPost.mockResolvedValue({ data: { emoji: ' 🎧 ', title: ' Weekly standup ' } })

    expect(await generateConversationTopic('we discussed the sprint')).toEqual({
      emoji: '🎧',
      title: 'Weekly standup'
    })
    expect(omiPost).toHaveBeenCalledWith('/v1/conversations/topic', {
      transcript: 'we discussed the sprint'
    })
  })

  it('stays null on an empty transcript, an empty topic, or a failed call', async () => {
    expect(await generateConversationTopic('   ')).toBeNull()
    expect(omiPost).not.toHaveBeenCalled()

    omiPost.mockResolvedValue({ data: { emoji: '', title: '' } })
    expect(await generateConversationTopic('anything')).toBeNull()

    omiPost.mockRejectedValue(new Error('boom'))
    expect(await generateConversationTopic('anything')).toBeNull()
  })
})
