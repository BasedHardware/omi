// Data-layer client: request shape + snake↔camel round-trip, and the
// shared-thread continuity guard (the default thread is never sent a
// session_id on reads/deletes). `./apiClient` is mocked so no real
// axios/Firebase loads. Message WRITES are `saveDesktopMessage`'s job
// (desktopChatMessages.ts) and tested there — not re-implemented here.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn()
}))

vi.mock('./apiClient', () => ({ omiApi: api }))

import {
  createSession,
  deleteMessages,
  deleteSession,
  getMessages,
  getSession,
  listSessions,
  updateSession
} from './chatSessionsClient'

// A representative wire (snake_case) session, as the backend serializes it.
const wireSession = {
  id: 'sess-1',
  title: 'My chat',
  preview: 'last message',
  created_at: '2026-07-14T10:00:00Z',
  updated_at: '2026-07-14T12:00:00Z',
  app_id: null,
  plugin_id: null,
  message_count: 4,
  starred: true
}

beforeEach(() => {
  api.post.mockReset()
  api.get.mockReset()
  api.patch.mockReset()
  api.delete.mockReset()
})

describe('createSession', () => {
  it('POSTs an empty body by default and maps the wire response to camelCase', async () => {
    api.post.mockResolvedValue({ data: wireSession })

    const session = await createSession()

    expect(api.post).toHaveBeenCalledWith('/v2/chat-sessions', {})
    expect(session).toEqual({
      id: 'sess-1',
      title: 'My chat',
      preview: 'last message',
      createdAt: '2026-07-14T10:00:00Z',
      updatedAt: '2026-07-14T12:00:00Z',
      appId: undefined,
      messageCount: 4,
      starred: true
    })
  })

  it('translates camelCase title/appId into the snake_case body', async () => {
    api.post.mockResolvedValue({ data: { ...wireSession, app_id: 'app-x', plugin_id: 'app-x' } })

    const session = await createSession({ title: 'Docs', appId: 'app-x' })

    expect(api.post).toHaveBeenCalledWith('/v2/chat-sessions', { title: 'Docs', app_id: 'app-x' })
    expect(session.appId).toBe('app-x')
  })
})

describe('listSessions', () => {
  it('sends NO query params by default (→ main-chat sessions only)', async () => {
    api.get.mockResolvedValue({ data: [wireSession] })

    const sessions = await listSessions()

    expect(api.get).toHaveBeenCalledWith('/v2/chat-sessions', { params: {} })
    expect(sessions).toHaveLength(1)
    expect(sessions[0].id).toBe('sess-1')
  })

  it('forwards starred/appId/limit/offset filters as snake_case query params', async () => {
    api.get.mockResolvedValue({ data: [] })

    await listSessions({ appId: 'app-x', starred: true, limit: 20, offset: 40 })

    expect(api.get).toHaveBeenCalledWith('/v2/chat-sessions', {
      params: { app_id: 'app-x', starred: true, limit: 20, offset: 40 }
    })
  })
})

describe('getSession', () => {
  it('GETs by id and maps the response', async () => {
    api.get.mockResolvedValue({ data: wireSession })
    const s = await getSession('sess-1')
    expect(api.get).toHaveBeenCalledWith('/v2/chat-sessions/sess-1')
    expect(s.starred).toBe(true)
  })
})

describe('updateSession', () => {
  it('PATCHes only the title on a rename', async () => {
    api.patch.mockResolvedValue({ data: { ...wireSession, title: 'Renamed' } })

    const s = await updateSession('sess-1', { title: 'Renamed' })

    expect(api.patch).toHaveBeenCalledWith('/v2/chat-sessions/sess-1', { title: 'Renamed' })
    expect(s.title).toBe('Renamed')
  })

  it('PATCHes only starred on a star toggle', async () => {
    api.patch.mockResolvedValue({ data: { ...wireSession, starred: false } })

    await updateSession('sess-1', { starred: false })

    expect(api.patch).toHaveBeenCalledWith('/v2/chat-sessions/sess-1', { starred: false })
  })
})

describe('deleteSession', () => {
  it('DELETEs by id (server cascades messages)', async () => {
    api.delete.mockResolvedValue({ data: { status: 'ok' } })
    await deleteSession('sess-1')
    expect(api.delete).toHaveBeenCalledWith('/v2/chat-sessions/sess-1')
  })
})

describe('getMessages / deleteMessages', () => {
  it('GETs the default thread with no session param and maps chat_session_id → sessionId', async () => {
    api.get.mockResolvedValue({
      data: [
        {
          id: 'm1',
          text: 'hey',
          created_at: '2026-07-14T12:00:00Z',
          sender: 'human',
          app_id: null,
          chat_session_id: null,
          rating: null
        }
      ]
    })

    const msgs = await getMessages()

    expect(api.get).toHaveBeenCalledWith('/v2/desktop/messages', { params: {} })
    expect(msgs[0]).toEqual({
      id: 'm1',
      text: 'hey',
      createdAt: '2026-07-14T12:00:00Z',
      sender: 'human',
      appId: undefined,
      sessionId: undefined,
      rating: undefined
    })
  })

  it('GETs a session thread with its session_id and maps chat_session_id → sessionId', async () => {
    api.get.mockResolvedValue({
      data: [
        {
          id: 'm2',
          text: 'in session',
          created_at: '2026-07-14T12:05:00Z',
          sender: 'ai',
          app_id: null,
          chat_session_id: 'sess-9',
          rating: null
        }
      ]
    })

    const msgs = await getMessages({ sessionId: 'sess-9' })

    expect(api.get).toHaveBeenCalledWith('/v2/desktop/messages', {
      params: { session_id: 'sess-9' }
    })
    expect(msgs[0].sessionId).toBe('sess-9')
  })

  it('maps a wire message`s files → attachments (with the public thumbnail URL)', async () => {
    api.get.mockResolvedValue({
      data: [
        {
          id: 'm3',
          text: 'here',
          created_at: '2026-07-14T12:10:00Z',
          sender: 'human',
          files: [
            {
              id: 'srv-img',
              name: 'photo.png',
              mime_type: 'image/png',
              thumbnail: 'https://cdn/x.png'
            },
            { id: 'srv-doc', name: 'report.pdf', mime_type: 'application/pdf', thumbnail: null }
          ]
        }
      ]
    })

    const msgs = await getMessages({ sessionId: 'sess-9' })

    expect(msgs[0].attachments).toEqual([
      {
        id: 'srv-img',
        name: 'photo.png',
        mimeType: 'image/png',
        thumbnailUrl: 'https://cdn/x.png'
      },
      { id: 'srv-doc', name: 'report.pdf', mimeType: 'application/pdf', thumbnailUrl: undefined }
    ])
  })

  it('omits attachments entirely when the wire message has no files', async () => {
    api.get.mockResolvedValue({
      data: [{ id: 'm4', text: 'plain', created_at: '2026-07-14T12:11:00Z', sender: 'human' }]
    })
    const msgs = await getMessages()
    expect('attachments' in msgs[0]).toBe(false)
  })

  it('DELETEs a session thread and returns the deleted count', async () => {
    api.delete.mockResolvedValue({ data: { status: 'ok', deleted_count: 7 } })

    const count = await deleteMessages({ sessionId: 'sess-9' })

    expect(api.delete).toHaveBeenCalledWith('/v2/desktop/messages', {
      params: { session_id: 'sess-9' }
    })
    expect(count).toBe(7)
  })
})
