// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import type {
  ChatMessage,
  MainChatEvent,
  MainChatResult,
  MainChatSendArgs
} from '../../../shared/types'

// The chat-app / persona picker threading (Mac ChatProvider.selectApp / selectedAppId).
// selectApp(id) must:
//   • thread `app_id` into the send path — a QUERY param on /v2/messages (legacy_sse)
//     and both the kernel chatId namespace + the INV-CHAT-1 saveDesktopMessage calls
//     (pi_mono);
//   • reset to the app's default chat (session cleared, transcript reloaded from the
//     server, scoped by app_id);
//   • leave the DEFAULT (no app selected) path byte-identical — no app_id anywhere,
//     and the human turn still saved EXACTLY once (INV-CHAT-1).

vi.mock('../lib/firebase', () => ({
  auth: { currentUser: { getIdToken: async () => 'test-token' } }
}))
vi.mock('../lib/pageCache', () => ({ invalidateConversationsCache: vi.fn() }))
vi.mock('../lib/localAgent', () => ({ gatherLocalContext: async () => '' }))
vi.mock('../lib/screenContext', () => ({ readCurrentScreen: async () => '' }))
vi.mock('../lib/actionPlanner', () => ({
  looksLikeAction: () => false,
  looksLikeRawPlan: () => false,
  planActions: vi.fn()
}))
vi.mock('../lib/agentLLM', () => ({ callAgentLLM: vi.fn() }))
vi.mock('../lib/agentTask', () => ({
  detectAgentTask: () => null,
  resolveTaskCwd: vi.fn(async () => '/tmp/cwd')
}))
vi.mock('../lib/preferences', () => ({
  getPreferences: () => ({
    chatHistoryMode: 'per-launch',
    automationConsentedAt: null,
    agentCommands: {}
  })
}))
vi.mock('../lib/voice/voiceController', () => ({ speakText: async () => {} }))
// INV-CHAT-1 shared-thread persistence — spied so we can assert the app_id + count.
const saveSpy = vi.fn(async (_req: Record<string, unknown>) => ({
  id: 's',
  createdAt: 'n',
  created: true
}))
vi.mock('../lib/desktopChatMessages', () => ({
  saveDesktopMessage: (req: Record<string, unknown>) => saveSpy(req)
}))
// selectApp reloads the app's default chat via getMessages({ appId }). Controllable.
const getMessagesSpy = vi.fn(async (_q: unknown): Promise<unknown[]> => [])
vi.mock('../lib/chatSessionsClient', () => ({ getMessages: (q: unknown) => getMessagesSpy(q) }))

import { useChat } from './useChat'
import { clearAttachments } from '../lib/chatAttachments'

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

// A successful terminal kernel result for the captured requestId/runId.
const okResult = (requestId: string, text: string): MainChatResult => ({
  runId: 'r1',
  requestId,
  ok: true,
  text,
  terminalStatus: 'succeeded'
})

beforeEach(() => {
  vi.clearAllMocks()
  clearAttachments()
  getMessagesSpy.mockReset()
  getMessagesSpy.mockResolvedValue([])
  saveSpy.mockClear()
})
afterEach(() => cleanup())

// ── pi_mono kernel path ────────────────────────────────────────────────────────
describe('useChat.selectApp — pi_mono kernel path', () => {
  let eventCb: ((e: MainChatEvent) => void) | null = null
  let sendArgs: MainChatSendArgs | null = null
  let sendResolve: ((r: MainChatResult) => void) | null = null

  beforeEach(() => {
    eventCb = null
    sendArgs = null
    sendResolve = null
    ;(window as unknown as { omi: unknown }).omi = {
      automationEnabled: false,
      chatGetEngine: async () => 'pi_mono',
      getLocalConversation: async () => null,
      insertLocalConversation: async () => {},
      notifyConversationsChanged: vi.fn(),
      onMainChatEvent: (cb: (e: MainChatEvent) => void) => {
        eventCb = cb
        return () => {
          if (eventCb === cb) eventCb = null
        }
      },
      mainChatSend: (args: MainChatSendArgs) => {
        sendArgs = args
        return new Promise<MainChatResult>((res) => (sendResolve = res))
      },
      mainChatCancel: vi.fn(async () => true),
      codingAgentCancel: vi.fn(async () => {})
    }
  })

  async function mount(): Promise<
    ReturnType<typeof renderHook<ReturnType<typeof useChat>, unknown>>['result']
  > {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await flush()
    })
    return result
  }
  async function waitForSend(): Promise<void> {
    for (let k = 0; k < 100 && !sendArgs; k++) await flush()
    if (!sendArgs) throw new Error('mainChatSend never called')
  }

  it('threads app_id into the kernel chatId namespace and both INV-CHAT-1 saves', async () => {
    const result = await mount()
    act(() => result.current.selectApp('persona-a'))
    expect(result.current.selectedAppId).toBe('persona-a')

    await act(async () => {
      const p = result.current.send('hello')
      await waitForSend()
      // Kernel conversation is namespaced to the app (Mac's "default|<appId>").
      expect(sendArgs?.chatId).toBe('app-persona-a')
      // The human turn is saved once, scoped by app_id (no session_id on default chat).
      // The spy receives the camelCase SaveDesktopMessageRequest (the snake_case wire
      // mapping is inside the real desktopChatMessages, mocked here).
      const humanSaves = saveSpy.mock.calls.filter(
        (c) => (c[0] as { sender: string }).sender === 'human'
      )
      expect(humanSaves).toHaveLength(1)
      expect(humanSaves[0][0]).toMatchObject({ appId: 'persona-a' })
      expect((humanSaves[0][0] as Record<string, unknown>).sessionId).toBeUndefined()
      // Complete the turn → the assistant save is app-scoped too.
      eventCb?.({ type: 'accepted', requestId: sendArgs!.requestId, runId: 'r1' })
      sendResolve?.(okResult(sendArgs!.requestId, 'hi there'))
      await p
    })
    const aiSaves = saveSpy.mock.calls.filter((c) => (c[0] as { sender: string }).sender === 'ai')
    expect(aiSaves).toHaveLength(1)
    expect(aiSaves[0][0]).toMatchObject({ appId: 'persona-a', text: 'hi there' })
  })

  it('DEFAULT (no app selected) is byte-identical — no app_id, chatId un-namespaced, one human save', async () => {
    const result = await mount()
    await act(async () => {
      const p = result.current.send('hello')
      await waitForSend()
      expect(sendArgs?.chatId).not.toContain('app-')
      const humanSaves = saveSpy.mock.calls.filter(
        (c) => (c[0] as { sender: string }).sender === 'human'
      )
      expect(humanSaves).toHaveLength(1)
      expect((humanSaves[0][0] as Record<string, unknown>).appId).toBeUndefined()
      eventCb?.({ type: 'accepted', requestId: sendArgs!.requestId, runId: 'r1' })
      sendResolve?.(okResult(sendArgs!.requestId, 'hi'))
      await p
    })
  })

  it('selectApp resets the session and reloads the app default chat from the server', async () => {
    getMessagesSpy.mockResolvedValueOnce([
      { id: 'm1', sender: 'human', text: 'prior q', createdAt: 'n' },
      { id: 'm2', sender: 'ai', text: 'prior a', createdAt: 'n' }
    ])
    const result = await mount()
    await act(async () => {
      result.current.selectApp('persona-a')
      await flush()
    })
    // Loaded the app-scoped server transcript (Mac loadDefaultChatMessages).
    expect(getMessagesSpy).toHaveBeenCalledWith({ appId: 'persona-a' })
    expect(result.current.history.map((m) => m.content)).toEqual(['prior q', 'prior a'])
    // Session cleared (back on the app default chat, not a session).
    expect(result.current.currentThreadId).toBeNull()
  })

  it('selectApp is a no-op when the app is already selected', async () => {
    const result = await mount()
    await act(async () => {
      result.current.selectApp('persona-a')
      await flush()
    })
    getMessagesSpy.mockClear()
    act(() => result.current.selectApp('persona-a'))
    expect(getMessagesSpy).not.toHaveBeenCalled()
  })

  it('selectApp(null) returns to the default thread (local conversation, no app_id)', async () => {
    const result = await mount()
    await act(async () => {
      result.current.selectApp('persona-a')
      await flush()
    })
    await act(async () => {
      result.current.selectApp(null)
      await flush()
    })
    expect(result.current.selectedAppId).toBeNull()
    await act(async () => {
      const p = result.current.send('back to default')
      await waitForSend()
      expect(sendArgs?.chatId).not.toContain('app-')
      const humanSaves = saveSpy.mock.calls.filter(
        (c) => (c[0] as { sender: string }).sender === 'human'
      )
      expect((humanSaves.at(-1)?.[0] as Record<string, unknown>).appId).toBeUndefined()
      eventCb?.({ type: 'accepted', requestId: sendArgs!.requestId, runId: 'r1' })
      sendResolve?.(okResult(sendArgs!.requestId, 'ok'))
      await p
    })
  })
})

// ── legacy_sse /v2/messages path ────────────────────────────────────────────────
describe('useChat.selectApp — legacy_sse path', () => {
  let urls: string[] = []

  beforeEach(() => {
    urls = []
    // Immediately-closing stream so send() resolves without extra plumbing.
    global.fetch = vi.fn(async (url: unknown) => {
      urls.push(String(url))
      const reader = { read: async () => ({ done: true, value: undefined }) }
      return { ok: true, body: { getReader: () => reader } } as unknown as Response
    }) as unknown as typeof fetch
    ;(window as unknown as { omi: unknown }).omi = {
      automationEnabled: false,
      // No chatGetEngine → engineRef stays 'legacy_sse' (the safe default).
      getLocalConversation: async () => null,
      insertLocalConversation: async (_c: { messages?: ChatMessage[] }) => {},
      notifyConversationsChanged: vi.fn(),
      codingAgentCancel: vi.fn(async () => {}),
      mainChatCancel: vi.fn(async () => true)
    }
  })

  it('appends ?app_id=<id> to /v2/messages when an app is selected', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await flush()
    })
    act(() => result.current.selectApp('persona-a'))
    await act(async () => {
      await result.current.send('scoped question')
    })
    expect(urls.some((u) => u.includes('/v2/messages?app_id=persona-a'))).toBe(true)
  })

  it('DEFAULT: the /v2/messages URL carries NO app_id (byte-identical)', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await flush()
    })
    await act(async () => {
      await result.current.send('plain question')
    })
    expect(urls.some((u) => u.endsWith('/v2/messages'))).toBe(true)
    expect(urls.some((u) => u.includes('app_id'))).toBe(false)
  })
})
