import { describe, it, expect, vi, beforeEach } from 'vitest'

// The saveMessage wire client: proves the POST body is snake_case and OMITS
// app_id/session_id (default-shared-thread contract) when the caller doesn't set
// them — the mechanical guard behind INV-CHAT-1 mobile continuity for pi_mono.

const postSpy = vi.fn(async (_url: string, _body: Record<string, unknown>) => ({
  data: { id: 'srv-1', createdAt: '2026-07-15T00:00:00Z', created: true }
}))
vi.mock('./apiClient', () => ({
  omiApi: { post: (url: string, body: Record<string, unknown>) => postSpy(url, body) }
}))

import { saveDesktopMessage } from './desktopChatMessages'

beforeEach(() => postSpy.mockClear())

describe('saveDesktopMessage', () => {
  it('posts snake_case and OMITS app_id/session_id for the default shared thread', async () => {
    const ack = await saveDesktopMessage({
      text: 'hello',
      sender: 'human',
      clientMessageId: 'msg-1'
    })
    expect(ack).toEqual({ id: 'srv-1', createdAt: '2026-07-15T00:00:00Z', created: true })
    expect(postSpy).toHaveBeenCalledTimes(1)
    const [url, body] = postSpy.mock.calls[0] as [string, Record<string, unknown>]
    expect(url).toBe('/v2/desktop/messages')
    expect(body).toEqual({
      text: 'hello',
      sender: 'human',
      client_message_id: 'msg-1',
      message_source: 'desktop_chat'
    })
    // The default-thread contract: neither key present (omitted, not null).
    expect('session_id' in body).toBe(false)
    expect('app_id' in body).toBe(false)
  })

  it('includes the optionals (snake_case) only when provided', async () => {
    await saveDesktopMessage({
      text: 'x',
      sender: 'ai',
      appId: 'app-9',
      sessionId: 'sess-9',
      metadata: '{"resources":[]}',
      messageSource: 'realtime_voice'
    })
    const [, body] = postSpy.mock.calls[0] as [string, Record<string, unknown>]
    expect(body).toEqual({
      text: 'x',
      sender: 'ai',
      app_id: 'app-9',
      session_id: 'sess-9',
      metadata: '{"resources":[]}',
      message_source: 'realtime_voice'
    })
  })

  it('returns null (never throws) when the POST fails — continuity is best-effort', async () => {
    postSpy.mockRejectedValueOnce(new Error('network'))
    await expect(saveDesktopMessage({ text: 'x', sender: 'ai' })).resolves.toBeNull()
  })
})
