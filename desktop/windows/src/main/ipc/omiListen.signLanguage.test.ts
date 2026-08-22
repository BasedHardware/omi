import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => {
  type Listener = (...args: unknown[]) => void

  class FakeWebSocket {
    static CONNECTING = 0
    static OPEN = 1
    static instances: FakeWebSocket[] = []
    readyState = FakeWebSocket.CONNECTING
    binaryType = ''
    private listeners = new Map<string, Listener[]>()

    constructor(public url: string) {
      FakeWebSocket.instances.push(this)
    }

    on(event: string, listener: Listener): void {
      const listeners = this.listeners.get(event) ?? []
      listeners.push(listener)
      this.listeners.set(event, listeners)
    }

    send(): void {
      void 0
    }

    close(): void {
      this.readyState = 3
    }

    simulateOpen(): void {
      this.readyState = FakeWebSocket.OPEN
      for (const listener of this.listeners.get('open') ?? []) listener()
    }

    simulateSegments(text: string): void {
      const payload = JSON.stringify([{ text }])
      for (const listener of this.listeners.get('message') ?? [])
        listener(Buffer.from(payload), false)
    }
  }

  const ipcHandlers = new Map<string, (...args: unknown[]) => unknown>()
  const sent: unknown[][] = []
  return {
    FakeWebSocket,
    ipcHandlers,
    sent,
    isSignLanguageEnabled: vi.fn(() => true),
    defaultSignOpts: vi.fn(() => ({ baseUrl: null, posesDir: undefined })),
    translateToGlosses: vi.fn()
  }
})

vi.mock('ws', () => ({ default: h.FakeWebSocket }))
vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, handler: (...args: unknown[]) => unknown) =>
      h.ipcHandlers.set(channel, handler),
    on: (channel: string, handler: (...args: unknown[]) => unknown) =>
      h.ipcHandlers.set(channel, handler)
  },
  webContents: {
    fromId: () => ({ isDestroyed: () => false, send: (...args: unknown[]) => h.sent.push(args) })
  }
}))
vi.mock('../integrations/signLanguage', () => ({
  defaultSignOpts: h.defaultSignOpts,
  translateToGlosses: h.translateToGlosses
}))
vi.mock('./integrations', () => ({ isSignLanguageEnabled: h.isSignLanguageEnabled }))
vi.mock('../agentKernel/byokStore', () => ({
  ByokKeyStore: class {
    getAllKeys(): Record<string, never> {
      return {}
    }
  }
}))
vi.mock('../auth/omiAuth', () => ({ decodeUidFromIdToken: vi.fn(() => null) }))

import { registerOmiListenHandlers } from './omiListen'

describe('omi-listen sign-language translation buffering', () => {
  beforeEach(() => {
    h.ipcHandlers.clear()
    h.sent.length = 0
    h.FakeWebSocket.instances.length = 0
    h.isSignLanguageEnabled.mockReturnValue(true)
    h.defaultSignOpts.mockClear()
    h.translateToGlosses.mockReset()
    registerOmiListenHandlers(() => true)
  })

  it('buffers segments during an in-flight translation and serializes the next request', async () => {
    let resolveFirst:
      | ((value: { originalText: string; poseUrl: string; glosses: [] }) => void)
      | undefined
    h.translateToGlosses.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve
        })
    )
    h.translateToGlosses.mockResolvedValue({
      originalText: 'pending',
      poseUrl: 'data:',
      glosses: []
    })

    const start = h.ipcHandlers.get('omi-listen:start')!
    const stop = h.ipcHandlers.get('omi-listen:stop')!
    start(
      { sender: { id: 1, once: vi.fn() } },
      { sessionId: 'sign-1', source: 'mic', token: 'token', deviceIdHash: 'device', language: 'en' }
    )
    const ws = h.FakeWebSocket.instances[0]
    ws.simulateOpen()
    ws.simulateSegments('first')
    ws.simulateSegments('second segment that stays pending until the first translation completes')

    expect(h.translateToGlosses).toHaveBeenCalledTimes(1)
    expect(h.translateToGlosses).toHaveBeenNthCalledWith(1, 'first', 'en', 'ase', {
      baseUrl: null,
      posesDir: undefined
    })

    resolveFirst!({ originalText: 'first', poseUrl: 'data:', glosses: [] })
    await new Promise((resolve) => setTimeout(resolve, 0))
    ws.simulateSegments('tail')

    expect(h.translateToGlosses).toHaveBeenCalledTimes(2)
    expect(h.translateToGlosses.mock.calls[1][0]).toContain('second segment')
    expect(h.translateToGlosses.mock.calls[1][0]).toContain('tail')
    stop({ sender: { id: 1 } }, 'sign-1')
  })
})
