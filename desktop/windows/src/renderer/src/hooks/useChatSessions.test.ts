// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ChatSession } from '../../../shared/chatSessions'
import { useChatSessions, type SessionsClientLike } from './useChatSessions'

function session(over: Partial<ChatSession> & { id: string }): ChatSession {
  return {
    id: over.id,
    title: over.title ?? 'New Chat',
    preview: over.preview,
    createdAt: over.createdAt ?? '2026-07-14T00:00:00Z',
    updatedAt: over.updatedAt ?? '2026-07-14T00:00:00Z',
    appId: over.appId,
    messageCount: over.messageCount ?? 0,
    starred: over.starred ?? false
  }
}

function makeClient(initial: ChatSession[]): {
  client: SessionsClientLike
  fns: {
    listSessions: ReturnType<typeof vi.fn>
    createSession: ReturnType<typeof vi.fn>
    updateSession: ReturnType<typeof vi.fn>
    deleteSession: ReturnType<typeof vi.fn>
  }
} {
  const fns = {
    listSessions: vi.fn(async (params?: { starred?: boolean }) =>
      params?.starred ? initial.filter((s) => s.starred) : initial
    ),
    createSession: vi.fn(async () => session({ id: 'new-1', title: 'New Chat' })),
    updateSession: vi.fn(async (id: string, patch: { title?: string; starred?: boolean }) => ({
      ...(initial.find((s) => s.id === id) ?? session({ id })),
      ...patch
    })),
    deleteSession: vi.fn(async () => {})
  }
  return { client: fns as unknown as SessionsClientLike, fns }
}

const render = (client: SessionsClientLike) => renderHook(() => useChatSessions({ client }))

beforeEach(() => vi.clearAllMocks())
afterEach(() => cleanup())

describe('useChatSessions — load', () => {
  it('loads main-chat sessions on mount (no starred filter) and clears loading', async () => {
    const { client, fns } = makeClient([session({ id: '1' }), session({ id: '2' })])
    const { result } = render(client)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fns.listSessions).toHaveBeenCalledWith({})
    expect(result.current.sessions).toHaveLength(2)
    expect(result.current.error).toBeNull()
    // Continuity: default selection is the shared thread (null), not a session id.
    expect(result.current.currentSessionId).toBeNull()
  })

  it('surfaces a load error and recovers on retryLoad', async () => {
    const { client, fns } = makeClient([session({ id: '1' })])
    fns.listSessions.mockRejectedValueOnce({ response: { data: { detail: 'boom' } } })
    const { result } = render(client)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe('boom')

    await act(async () => {
      result.current.retryLoad()
    })
    await waitFor(() => expect(result.current.error).toBeNull())
    expect(result.current.sessions).toHaveLength(1)
  })
})

describe('useChatSessions — mutations', () => {
  it('createNewSession prepends the created session and selects it', async () => {
    const { client } = makeClient([session({ id: '1' })])
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.createNewSession()
    })
    expect(result.current.sessions[0].id).toBe('new-1')
    expect(result.current.currentSessionId).toBe('new-1')
  })

  it('a createNewSession failure sets createError ONLY — list/error/loading untouched', async () => {
    const { client, fns } = makeClient([session({ id: '1' }), session({ id: '2' })])
    fns.createSession.mockRejectedValueOnce({ response: { data: { detail: 'create failed' } } })
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      const created = await result.current.createNewSession()
      expect(created).toBeNull()
    })

    // The regression: a failed "+" must NOT mislabel the loaded list.
    expect(result.current.createError).toBe('create failed')
    expect(result.current.error).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(result.current.sessions.map((s) => s.id)).toEqual(['1', '2'])
    expect(result.current.currentSessionId).toBeNull()

    // clearCreateError dismisses the transient notice.
    act(() => result.current.clearCreateError())
    expect(result.current.createError).toBeNull()
  })

  it('renameSession no-ops on empty or unchanged titles', async () => {
    const { client, fns } = makeClient([session({ id: '1', title: 'Keep' })])
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.renameSession('1', '   ')
      await result.current.renameSession('1', 'Keep')
    })
    expect(fns.updateSession).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.renameSession('1', 'Renamed')
    })
    expect(fns.updateSession).toHaveBeenCalledWith('1', { title: 'Renamed' })
    expect(result.current.sessions[0].title).toBe('Renamed')
  })

  it('surfaces an error (never an unhandled rejection) when a mutation fails', async () => {
    const { client, fns } = makeClient([session({ id: '1', starred: false })])
    fns.updateSession.mockRejectedValueOnce({ response: { data: { detail: 'nope' } } })
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.toggleStar('1') // must resolve, not reject
    })
    expect(result.current.error).toBe('nope')
    expect(result.current.sessions[0].starred).toBe(false) // no optimistic flip on failure
  })

  it('toggleStar flips the flag locally when the starred filter is off', async () => {
    const { client, fns } = makeClient([session({ id: '1', starred: false })])
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.toggleStar('1')
    })
    expect(fns.updateSession).toHaveBeenCalledWith('1', { starred: true })
    expect(result.current.sessions[0].starred).toBe(true)
  })

  it('removeSession drops the row and returns to the shared thread if it was open', async () => {
    const { client, fns } = makeClient([session({ id: '1' }), session({ id: '2' })])
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.selectSession('1'))
    expect(result.current.currentSessionId).toBe('1')

    await act(async () => {
      await result.current.removeSession('1')
    })
    expect(fns.deleteSession).toHaveBeenCalledWith('1')
    expect(result.current.sessions.map((s) => s.id)).toEqual(['2'])
    expect(result.current.currentSessionId).toBeNull()
  })
})

describe('useChatSessions — filter & search', () => {
  it('toggleStarredFilter re-queries the server with starred=true', async () => {
    const { client, fns } = makeClient([
      session({ id: '1', starred: false }),
      session({ id: '2', starred: true })
    ])
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.toggleStarredFilter())
    await waitFor(() => expect(result.current.showStarredOnly).toBe(true))
    await waitFor(() => expect(fns.listSessions).toHaveBeenLastCalledWith({ starred: true }))
    expect(result.current.sessions.map((s) => s.id)).toEqual(['2'])
  })

  it('search filters client-side without re-querying', async () => {
    const { client, fns } = makeClient([
      session({ id: '1', title: 'Berlin trip' }),
      session({ id: '2', title: 'Groceries' })
    ])
    const { result } = render(client)
    await waitFor(() => expect(result.current.loading).toBe(false))
    const callsBefore = fns.listSessions.mock.calls.length

    act(() => result.current.setSearchQuery('berlin'))
    expect(result.current.filteredSessions.map((s) => s.id)).toEqual(['1'])
    // No extra server query — search is purely client-side.
    expect(fns.listSessions.mock.calls.length).toBe(callsBefore)
  })
})

describe('useChatSessions — app scoping (persona picker)', () => {
  it('threads app_id into the session list + create when an app is selected', async () => {
    const { client, fns } = makeClient([session({ id: '1', appId: 'persona-a' })])
    const { result } = renderHook(() => useChatSessions({ client, appId: 'persona-a' }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fns.listSessions).toHaveBeenCalledWith({ appId: 'persona-a' })

    await act(async () => {
      await result.current.createNewSession()
    })
    expect(fns.createSession).toHaveBeenCalledWith({ appId: 'persona-a' })
  })

  it('DEFAULT (no appId) queries the plain main-chat list — byte-identical', async () => {
    const { client, fns } = makeClient([session({ id: '1' })])
    const { result } = renderHook(() => useChatSessions({ client }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fns.listSessions).toHaveBeenCalledWith({})

    await act(async () => {
      await result.current.createNewSession()
    })
    expect(fns.createSession).toHaveBeenCalledWith({})
  })

  it('clears the session selection when the selected app changes (Mac selectApp)', async () => {
    const { client } = makeClient([session({ id: '1', appId: 'persona-a' })])
    const { result, rerender } = renderHook(
      ({ appId }: { appId: string | null }) => useChatSessions({ client, appId }),
      { initialProps: { appId: 'persona-a' as string | null } }
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    act(() => result.current.selectSession('1'))
    expect(result.current.currentSessionId).toBe('1')

    // Switch apps → the prior session selection is dropped.
    rerender({ appId: 'persona-b' })
    await waitFor(() => expect(result.current.currentSessionId).toBeNull())
  })
})
