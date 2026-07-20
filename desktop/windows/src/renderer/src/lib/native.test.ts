import { describe, expect, it, vi } from 'vitest'

const tauri = vi.hoisted(() => ({
  listen: vi.fn(),
  invoke: vi.fn()
}))

vi.mock('@tauri-apps/api/event', () => ({ listen: tauri.listen }))
vi.mock('@tauri-apps/api/core', () => ({ invoke: tauri.invoke }))

import { native, overlay } from './native'

describe('native event subscriptions', () => {
  it('unsubscribes when cleanup runs before Tauri finishes subscribing', async () => {
    let resolve: ((unlisten: () => void) => void) | undefined
    const unlisten = vi.fn()
    tauri.listen.mockReturnValueOnce(new Promise((next) => { resolve = next }))

    const stop = native.onConversationsChanged(vi.fn())
    stop()
    resolve?.(unlisten)
    await Promise.resolve()

    expect(unlisten).toHaveBeenCalledOnce()
  })

  it('reports native subscription failures', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    tauri.listen.mockRejectedValueOnce(new Error('bridge unavailable'))

    native.onConversationsChanged(vi.fn())
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(error).toHaveBeenCalledWith(
      'Failed to subscribe to native event omi://conversations-changed:',
      expect.any(Error)
    )
    error.mockRestore()
  })

  it('waits for the summon subscription before enabling the shortcut', async () => {
    const unlisten = vi.fn()
    tauri.listen.mockResolvedValueOnce(unlisten)

    const stop = await overlay.onSummonedReady(vi.fn())

    expect(tauri.listen).toHaveBeenCalledWith('omi://overlay-summoned', expect.any(Function))
    stop()
    expect(unlisten).toHaveBeenCalledOnce()
  })

  it('exposes asynchronous overlay failures', async () => {
    let listener: ((event: { payload: string }) => void) | undefined
    tauri.listen.mockImplementationOnce((_event: string, next: (event: { payload: string }) => void) => {
      listener = next
      return Promise.resolve(vi.fn())
    })
    const failure = vi.fn()

    overlay.onError(failure)
    await Promise.resolve()
    listener?.({ payload: 'shortcut unavailable' })

    expect(failure).toHaveBeenCalledWith('shortcut unavailable')
  })
})
