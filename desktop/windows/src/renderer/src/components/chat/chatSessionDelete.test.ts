// Regression: deleting the ACTIVE chat session must re-thread the engine back to
// the default shared thread (useChatSessions and useChat are separate hooks, so a
// bare removeSession leaves chat.currentThreadId/sessionIdRef pointing at the
// deleted id). deleteAndRethread owns that pairing.
import { describe, expect, it, vi } from 'vitest'
import { deleteAndRethread } from './chatSessionDelete'

describe('deleteAndRethread', () => {
  it('re-threads to the default thread when the ACTIVE session is deleted', async () => {
    const removeSession = vi.fn(async () => {})
    const switchThread = vi.fn()

    await deleteAndRethread(removeSession, 'sess-A', switchThread, 'sess-A')

    expect(removeSession).toHaveBeenCalledWith('sess-A')
    // Engine reset to the default shared thread (switchThread(null) → currentThreadId/sessionIdRef null).
    expect(switchThread).toHaveBeenCalledWith(null)
  })

  it('leaves the current thread untouched when a NON-active session is deleted', async () => {
    const removeSession = vi.fn(async () => {})
    const switchThread = vi.fn()

    await deleteAndRethread(removeSession, 'sess-A', switchThread, 'sess-B')

    expect(removeSession).toHaveBeenCalledWith('sess-B')
    expect(switchThread).not.toHaveBeenCalled()
  })

  it('does NOT re-thread when the delete fails (removeSession rejects)', async () => {
    const removeSession = vi.fn(async () => {
      throw new Error('delete failed')
    })
    const switchThread = vi.fn()

    // Must not reject — the UI fires it fire-and-forget.
    await expect(
      deleteAndRethread(removeSession, 'sess-A', switchThread, 'sess-A')
    ).resolves.toBeUndefined()
    expect(switchThread).not.toHaveBeenCalled()
  })

  it('deleting the active session while ON the default thread is a no-op re-thread', async () => {
    // currentThreadId null (default thread) can never equal a real session id, so
    // deleting any session from the default thread does not re-thread.
    const removeSession = vi.fn(async () => {})
    const switchThread = vi.fn()

    await deleteAndRethread(removeSession, null, switchThread, 'sess-A')

    expect(removeSession).toHaveBeenCalledWith('sess-A')
    expect(switchThread).not.toHaveBeenCalled()
  })
})
