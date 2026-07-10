import { describe, it, expect, vi, beforeAll } from 'vitest'

// Regression: releasing a PTT hold while the WebSocket is still CONNECTING used to
// drop the 'finalize' frame entirely (finalizeSession returned unless OPEN), so the
// backend waited out Deepgram's slow silence endpointing — the "transcribing forever
// / does nothing" symptom. The fix queues the finalize and sends it on 'open', right
// after the pre-connect audio flush.

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
  start: (sessionId: string) =>
    h.ipcHandlers.get('omi-listen:start')!(
      { sender: { id: 1 } },
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

describe('PTT finalize vs. connect race', () => {
  it('queues finalize sent while CONNECTING and delivers it on open, AFTER the audio flush', () => {
    ipc.start('race-1')
    const ws = lastWs()
    // Hold released mid-handshake: audio buffered, finalize requested — nothing on
    // the wire yet (socket not open).
    ipc.feed('race-1', 8192)
    ipc.finalize('race-1')
    expect(ws.sent).toHaveLength(0)

    ws.simulateOpen()
    // Buffered audio first, then the queued finalize — order matters, or the
    // backend would finalize before it has the speech.
    expect(ws.sent).toHaveLength(2)
    expect(Buffer.isBuffer(ws.sent[0])).toBe(true)
    expect(ws.sent[1]).toBe('finalize')
  })

  it('sends finalize immediately when the socket is already OPEN', () => {
    ipc.start('open-1')
    const ws = lastWs()
    ws.simulateOpen()
    ipc.finalize('open-1')
    expect(ws.sent).toContain('finalize')
  })

  it('does not resend a queued finalize on a later finalize call', () => {
    ipc.start('dedupe-1')
    const ws = lastWs()
    ipc.finalize('dedupe-1')
    ws.simulateOpen()
    expect(ws.sent.filter((m) => m === 'finalize')).toHaveLength(1)
  })

  it('drops audio fed after finalize while still CONNECTING (release seals the capture)', () => {
    // Regression: post-release speech used to keep streaming and land in the
    // transcript ("said okay after letting go and it picked it up").
    ipc.start('seal-1')
    const ws = lastWs()
    ipc.feed('seal-1', 8192) // spoken during the hold — kept
    ipc.finalize('seal-1') // key released
    ipc.feed('seal-1', 4096) // spoken after release — must be dropped
    ws.simulateOpen()
    expect(ws.sent).toHaveLength(2) // held audio + 'finalize', nothing else
    expect(Buffer.isBuffer(ws.sent[0])).toBe(true)
    expect((ws.sent[0] as Buffer).byteLength).toBe(8192)
    expect(ws.sent[1]).toBe('finalize')
  })

  it('drops audio fed after finalize on an OPEN socket', () => {
    ipc.start('seal-2')
    const ws = lastWs()
    ws.simulateOpen()
    ipc.feed('seal-2', 8192)
    ipc.finalize('seal-2')
    ipc.feed('seal-2', 4096) // post-release — dropped
    expect(ws.sent).toHaveLength(2)
    expect(ws.sent[1]).toBe('finalize')
  })
})
