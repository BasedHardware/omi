// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Drive the Memories page's window-focus revalidation. The data hook is mocked
// so we can assert exactly when `refresh` fires; the brain-map hook returns an
// empty graph so the WebGL canvas (unavailable in jsdom) is never mounted, and
// firebase is stubbed so `auth.currentUser` gates the refetch without a live
// session (mirrors HomeGoalsChips.test).
const refresh = vi.fn()
let loading = false

vi.mock('../hooks/useMemories', () => ({
  useMemories: () => ({
    memories: [],
    loading,
    error: null,
    canonicalLifecycleExposed: false,
    createMemory: vi.fn(),
    editMemory: vi.fn(),
    setMemoryVisibility: vi.fn(),
    deleteMemory: vi.fn(),
    refresh
  })
}))

vi.mock('../hooks/useMemoryGraph', () => ({
  useMemoryGraph: () => ({
    graph: { nodes: [], edges: [] },
    centerNodeId: undefined,
    rebuild: vi.fn(),
    rebuilding: false
  })
}))

vi.mock('../lib/toast', () => ({ toast: vi.fn() }))
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }
}))

// Signed-in by default; a test flips this to null to exercise the auth guard.
const firebaseMock = { auth: { currentUser: { uid: 'u1' } as { uid: string } | null } }
vi.mock('../lib/firebase', () => firebaseMock)

async function renderPage(): Promise<void> {
  const { Memories } = await import('./Memories')
  render(
    <MemoryRouter>
      <Memories />
    </MemoryRouter>
  )
}

beforeEach(() => {
  refresh.mockReset().mockResolvedValue(undefined)
  loading = false
  firebaseMock.auth.currentUser = { uid: 'u1' }
})

afterEach(() => {
  cleanup()
  vi.resetModules()
})

describe('Memories — revalidates on window focus', () => {
  it('calls refresh when the window regains focus', async () => {
    await renderPage()
    expect(refresh).not.toHaveBeenCalled()

    fireEvent(window, new Event('focus'))
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('does not refresh while the initial load is still in flight (loading guard)', async () => {
    loading = true
    await renderPage()

    fireEvent(window, new Event('focus'))
    expect(refresh).not.toHaveBeenCalled()
  })

  it('does not refresh when signed out (auth guard)', async () => {
    firebaseMock.auth.currentUser = null
    await renderPage()

    fireEvent(window, new Event('focus'))
    expect(refresh).not.toHaveBeenCalled()
  })

  it('removes the focus listener on unmount', async () => {
    await renderPage()
    cleanup()

    fireEvent(window, new Event('focus'))
    expect(refresh).not.toHaveBeenCalled()
  })
})
