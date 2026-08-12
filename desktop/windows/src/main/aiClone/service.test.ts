import { describe, expect, it, vi } from 'vitest'
import type { AiCloneDraft } from '../../shared/types'

import { AiCloneService } from './service'

type ServiceInternals = {
  client: {
    listMessages: (chatId: string) => Promise<{ ok: true; value: [] }>
  }
  firebaseToken: string | null
  sessionStartedAt: number
  chatCache: Map<
    string,
    { id: string; title?: string; network?: string; type?: 'single' | 'group' }
  >
  processed: Set<string>
  store: {
    getBeeperToken: () => null
    getEnabled: () => false
    getChatMode: (chatId: string) => 'draft'
    getDrafts: () => AiCloneDraft[]
    getActivity: () => []
    upsertDraft: (draft: AiCloneDraft) => void
    addActivity: () => void
    setEnabled?: (enabled: boolean) => void
  }
  handleIncoming: (chatId: string, message: { id: string; text: string; timestamp: number }) => void
}

describe('AiCloneService', () => {
  it('retries an inbound message after a failed response and marks it processed only once a draft exists', async () => {
    const drafts: AiCloneDraft[] = []
    const replyGenerator = vi.fn()
    const service = new AiCloneService(vi.fn(), replyGenerator) as unknown as ServiceInternals
    service.client = { listMessages: vi.fn().mockResolvedValue({ ok: true, value: [] }) }
    service.sessionStartedAt = 0
    service.chatCache.set('chat-1', { id: 'chat-1', title: 'Alice' })
    service.store = {
      getBeeperToken: () => null,
      getEnabled: () => false,
      getChatMode: () => 'draft',
      getDrafts: () => drafts,
      getActivity: () => [],
      upsertDraft: (draft) => drafts.push(draft),
      addActivity: vi.fn()
    }
    const message = { id: 'message-1', text: 'Can we catch up?', timestamp: Date.now() }

    service.handleIncoming('chat-1', message)
    await vi.waitFor(() => expect(service.store.addActivity).toHaveBeenCalledOnce())
    expect(service.processed).not.toContain(message.id)
    expect(replyGenerator).not.toHaveBeenCalled()

    service.firebaseToken = 'fresh-token'
    replyGenerator.mockResolvedValue({ ok: true, text: 'Sure, how about tomorrow?' })
    service.handleIncoming('chat-1', message)

    await vi.waitFor(() => expect(drafts).toHaveLength(1))
    expect(service.processed).toContain(message.id)
  })

  it('drops a reply that was still generating when the user turned the clone off', async () => {
    const drafts: AiCloneDraft[] = []
    let release: (result: { ok: true; text: string }) => void = () => {}
    const replyGenerator = vi.fn().mockReturnValue(
      new Promise<{ ok: true; text: string }>((resolve) => {
        release = resolve
      })
    )
    const real = new AiCloneService(vi.fn(), replyGenerator)
    const service = real as unknown as ServiceInternals
    service.client = { listMessages: vi.fn().mockResolvedValue({ ok: true, value: [] }) }
    service.firebaseToken = 'token'
    service.sessionStartedAt = 0
    service.chatCache.set('chat-1', { id: 'chat-1', title: 'Alice' })
    service.store = {
      getBeeperToken: () => null,
      getEnabled: () => false,
      getChatMode: () => 'draft',
      getDrafts: () => drafts,
      getActivity: () => [],
      upsertDraft: (draft) => drafts.push(draft),
      addActivity: vi.fn(),
      setEnabled: vi.fn()
    }

    service.handleIncoming('chat-1', { id: 'm1', text: 'hey', timestamp: Date.now() })
    await vi.waitFor(() => expect(replyGenerator).toHaveBeenCalledOnce())

    // Turning it off happens while the model is still answering. That reply must
    // not appear as a pending draft afterwards.
    real.setEnabled(false)
    release({ ok: true, text: 'sure, tomorrow works' })

    await vi.waitFor(() => expect(replyGenerator).toHaveBeenCalledOnce())
    expect(drafts).toHaveLength(0)
    expect(service.processed).not.toContain('m1')
  })
})
