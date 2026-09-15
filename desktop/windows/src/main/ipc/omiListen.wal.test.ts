import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'

// The audio the listen socket does not take used to end at a silent `return`,
// so a network drop mid-conversation lost that audio for good. These tests pin
// the three ways that happens, from the socket's point of view: no session at
// all, the bounded pre-connect buffer overflowing, and a socket that is closing
// or already closed. Each must be reported so the write-ahead log can keep it.

const h = vi.hoisted(() => {
  type Listener = (...args: unknown[]) => void
  class FakeWebSocket {
    static CONNECTING = 0
    static OPEN = 1
    static CLOSING = 2
    static CLOSED = 3
    static instances: FakeWebSocket[] = []
    readyState = FakeWebSocket.CONNECTING
    binaryType = ''
    sent: unknown[] = []
    private listeners = new Map<string, Listener[]>()
    constructor(public url: string) {
      FakeWebSocket.instances.push(this)
    }
    on(ev: string, fn: Listener): void {
      const arr = this.listeners.get(ev) ?? []
      arr.push(fn)
      this.listeners.set(ev, arr)
    }
    emit(ev: string, ...args: unknown[]): void {
      for (const fn of this.listeners.get(ev) ?? []) fn(...args)
    }
    send(data: unknown): void {
      this.sent.push(data)
    }
    close(): void {
      this.readyState = FakeWebSocket.CLOSED
    }
    open(): void {
      this.readyState = FakeWebSocket.OPEN
      this.emit('open')
    }
  }
  const handlers = new Map<string, (...args: unknown[]) => unknown>()
  return { FakeWebSocket, handlers }
})

vi.mock('ws', () => ({ default: h.FakeWebSocket }))
vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, fn: (...args: unknown[]) => unknown) => h.handlers.set(channel, fn),
    on: (channel: string, fn: (...args: unknown[]) => unknown) => h.handlers.set(channel, fn),
    removeHandler: () => undefined
  },
  webContents: { fromId: () => null },
  app: { getPath: () => '/tmp' },
  BrowserWindow: { getAllWindows: () => [] }
}))

import {
  registerOmiListenHandlers,
  setListenFeedObserver,
  type ListenFeedObserver
} from './omiListen'
import { PCM_PENDING_MAX_BYTES } from '../../shared/types'

interface Observed {
  source: string
  byteLength: number
  disposition: string
}

let observed: Observed[] = []
let resolved: Array<{ source: string; disposition: string; count?: number }> = []

const observer: ListenFeedObserver = {
  observe: (args) =>
    observed.push({
      source: args.source,
      byteLength: args.byteLength,
      disposition: args.disposition
    }),
  resolveBuffered: (source, disposition, count) => resolved.push({ source, disposition, count })
}

const sender = { id: 1, once: () => undefined, isDestroyed: () => false }
const startSession = async (sessionId: string): Promise<void> => {
  const start = h.handlers.get('omi-listen:start')!
  await start(
    { sender },
    {
      sessionId,
      source: 'mic',
      token: 't',
      deviceIdHash: 'd',
      language: 'en',
      mode: 'conversation'
    }
  )
}

const feed = (sessionId: string, bytes: number): void => {
  const fn = h.handlers.get('omi-listen:feed')!
  fn({ sender }, sessionId, new ArrayBuffer(bytes))
}

const latestSocket = (): InstanceType<typeof h.FakeWebSocket> =>
  h.FakeWebSocket.instances[h.FakeWebSocket.instances.length - 1]

beforeAll(() => {
  registerOmiListenHandlers(() => true)
})

beforeEach(() => {
  observed = []
  resolved = []
  h.FakeWebSocket.instances = []
  setListenFeedObserver(observer)
})

describe('audio the socket takes', () => {
  it('is reported as sent, not kept', async () => {
    await startSession('s1')
    latestSocket().open()
    feed('s1', 3200)
    expect(observed).toEqual([{ source: 'mic', byteLength: 3200, disposition: 'sent' }])
  })
})

describe('audio the socket does not take', () => {
  it('reports a chunk fed after the server closed the socket', async () => {
    await startSession('s-dead')
    const socket = latestSocket()
    socket.open()
    // The backend closes the socket; the renderer is still capturing and keeps
    // feeding. Ownership outlives the session, so those chunks reach the feed
    // path with no session behind them, where this used to be a silent
    // `return` and the audio was gone.
    socket.readyState = h.FakeWebSocket.CLOSED
    socket.emit('close', 1006, Buffer.from(''))
    observed = []

    feed('s-dead', 3200)
    expect(observed).toEqual([{ source: 'mic', byteLength: 3200, disposition: 'missed' }])
  })

  it('reports a chunk fed to a closed socket', async () => {
    await startSession('s2')
    latestSocket().readyState = h.FakeWebSocket.CLOSED
    feed('s2', 3200)
    expect(observed).toEqual([{ source: 'mic', byteLength: 3200, disposition: 'missed' }])
  })

  it('reports pre-connect audio as buffered, then as sent once it is flushed', async () => {
    await startSession('s3')
    feed('s3', 3200)
    feed('s3', 3200)
    expect(observed.every((o) => o.disposition === 'buffered')).toBe(true)

    latestSocket().open()
    // The open handler flushed both, so they did reach the backend.
    expect(resolved).toEqual([{ source: 'mic', disposition: 'sent', count: 2 }])
  })

  it('reports pre-connect audio evicted past the buffer cap as missed', async () => {
    await startSession('s4')
    // The buffer holds five seconds; feeding past it evicts the oldest.
    const chunk = 32_000
    const chunks = Math.ceil(PCM_PENDING_MAX_BYTES / chunk) + 3
    for (let i = 0; i < chunks; i += 1) feed('s4', chunk)

    const evicted = resolved.filter((r) => r.disposition === 'missed')
    expect(evicted.length).toBeGreaterThan(0)
    // Everything fed was still observed, so nothing vanished unaccounted for.
    expect(observed.length).toBe(chunks)
  })

  it('reports the discarded buffer when a session is superseded', async () => {
    await startSession('s5')
    feed('s5', 3200)
    // Starting another session for the same window kills the first, which
    // throws away its pending buffer.
    await startSession('s5')
    expect(resolved.some((r) => r.disposition === 'missed')).toBe(true)
  })
})

describe('observer lifecycle', () => {
  it('feeding without an observer is safe', async () => {
    setListenFeedObserver(null)
    await startSession('s6')
    expect(() => feed('s6', 3200)).not.toThrow()
    expect(observed).toEqual([])
  })
})
