import { describe, it, expect, vi, beforeAll } from 'vitest'

// Main-process PTT lane contract:
// - Audio fed while the socket is CONNECTING is buffered and flushed on 'open',
//   in order — speech during the handshake is never lost to the stream lane.
// - 'finalize' is only sent on an OPEN socket. The renderer only requests it
//   after observing 'connected'; a not-open call is a no-op (a hold released
//   mid-handshake batch-transcribes its locally-retained buffer instead).
// - A new PTT hold supersedes any prior PTT session for the same window, so
//   handshakes never pile up and contend (the old hold's stream death just means
//   it falls back to batch).

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
    send(data: unknown): void {
      this.sent.push(data)
    }
    close(): void {
      this.readyState = FakeWebSocket.CLOSED
    }
    simulateOpen(): void {
      this.readyState = FakeWebSocket.OPEN
      for (const fn of this.listeners.get('open') ?? []) fn()
    }
  }
  const ipcHandlers = new Map<string, (...args: unknown[]) => void>()
  return { FakeWebSocket, ipcHandlers }
})

vi.mock('ws', () => ({ default: h.FakeWebSocket }))
vi.mock('electron', () => ({
  ipcMain: {
    handle: (ch: string, fn: (...args: unknown[]) => void) => h.ipcHandlers.set(ch, fn),
    on: (ch: string, fn: (...args: unknown[]) => void) => h.ipcHandlers.set(ch, fn)
  },
  webContents: {
    fromId: () => ({ isDestroyed: () => false, send: () => {} })
  }
}))

import { registerOmiListenHandlers } from './omiListen'

const ipc = {
  start: (sessionId: string, ownerId = 1) =>
    h.ipcHandlers.get('omi-listen:start')!(
      { sender: { id: ownerId } },
      { sessionId, token: 'tok', language: 'en', source: 'mic', mode: 'ptt' }
    ),
  feed: (sessionId: string, bytes: number) =>
    h.ipcHandlers.get('omi-listen:feed')!(null, sessionId, new ArrayBuffer(bytes)),
  finalize: (sessionId: string) => h.ipcHandlers.get('omi-listen:finalize')!(null, sessionId)
}

function lastWs(): InstanceType<typeof h.FakeWebSocket> {
  return h.FakeWebSocket.instances[h.FakeWebSocket.instances.length - 1]
}

beforeAll(() => {
  registerOmiListenHandlers()
})

describe('PTT stream lane', () => {
  it('buffers pre-OPEN audio and flushes it in order on open', () => {
    ipc.start('flush-1')
    const ws = lastWs()
    ipc.feed('flush-1', 8192)
    ipc.feed('flush-1', 4096)
    expect(ws.sent).toHaveLength(0)
    ws.simulateOpen()
    expect(ws.sent).toHaveLength(2)
    expect((ws.sent[0] as Buffer).byteLength).toBe(8192)
    expect((ws.sent[1] as Buffer).byteLength).toBe(4096)
  })

  it('sends finalize on an OPEN socket', () => {
    ipc.start('open-1')
    const ws = lastWs()
    ws.simulateOpen()
    ipc.finalize('open-1')
    expect(ws.sent).toContain('finalize')
  })

  it('finalize while still CONNECTING is a no-op (renderer contract: batch instead)', () => {
    ipc.start('early-1')
    const ws = lastWs()
    ipc.feed('early-1', 8192)
    ipc.finalize('early-1')
    ws.simulateOpen()
    // The buffered audio flushes, but no finalize was queued or sent.
    expect(ws.sent.filter((m) => m === 'finalize')).toHaveLength(0)
    expect(ws.sent).toHaveLength(1)
  })

  it('a new PTT hold supersedes the prior PTT session for the same window', () => {
    ipc.start('hold-a', 7)
    const first = lastWs()
    ipc.start('hold-b', 7)
    const second = lastWs()
    expect(first.readyState).toBe(h.FakeWebSocket.CLOSED)
    expect(second.readyState).toBe(h.FakeWebSocket.CONNECTING)
    // The superseded session is gone — feeding it is a no-op.
    ipc.feed('hold-a', 8192)
    second.simulateOpen()
    expect(first.sent).toHaveLength(0)
  })

  it('does not supersede a different window\'s PTT session', () => {
    ipc.start('win1-hold', 11)
    const first = lastWs()
    ipc.start('win2-hold', 12)
    expect(first.readyState).toBe(h.FakeWebSocket.CONNECTING)
  })
})
