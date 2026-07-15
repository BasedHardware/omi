import { EventEmitter } from 'node:events'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { OP_HELLO, OP_MUTE, OP_RESTORE, PROTOCOL_VERSION } from './protocol'

// The main-process half of PTT system-audio muting (Track 2 A4). What matters
// here is that the PTT path can NEVER be broken or blocked by the helper:
//   * helper binary absent (no .NET SDK at build) ⇒ every call is a silent no-op
//     and we stop re-spawning a missing exe;
//   * a live helper gets the right opcodes, in order, behind a version handshake.

const spawnMock = vi.fn()
vi.mock('node:child_process', () => ({ spawn: (...a: unknown[]) => spawnMock(...a) }))
vi.mock('child_process', () => ({ spawn: (...a: unknown[]) => spawnMock(...a) }))
vi.mock('./resolveHelperPath', () => ({
  resolveAudioHelperPath: () => 'C:/nonexistent/win-audio-helper.exe'
}))
// The bridge emits a durable Sentry diagnostic when the helper is confirmed
// missing/incompatible — a field user's "PTT doesn't mute my music" must not be
// silent. Mock it so we can assert it fires (exactly once, behind the guard).
const captureMessageMock = vi.fn()
vi.mock('../sentry', () => ({ captureMessage: (...a: unknown[]) => captureMessageMock(...a) }))

type FakeChild = EventEmitter & {
  stdout: EventEmitter
  stderr: EventEmitter
  stdin: { write: (b: Buffer) => void; end: () => void }
  kill: () => void
  killed: boolean
  stdinEnded: boolean
}

/** `onWrite` sees the decoded request: [uint32 LE len][1 byte opcode][UTF-8 JSON]. */
function makeChild(
  onWrite: (opcode: number, payload: string, child: FakeChild) => void
): FakeChild {
  const child = new EventEmitter() as FakeChild
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  child.killed = false
  child.stdinEnded = false
  child.kill = () => {
    child.killed = true
  }
  child.stdin = {
    write: (frame: Buffer) =>
      onWrite(frame.readUInt8(4), frame.subarray(5).toString('utf8'), child),
    end: () => {
      child.stdinEnded = true
    }
  }
  return child
}

/** Respond with a [uint32 LE len][UTF-8 JSON] frame, like the real helper. */
function reply(child: FakeChild, json: string): void {
  const body = Buffer.from(json, 'utf8')
  const header = Buffer.alloc(4)
  header.writeUInt32LE(body.length, 0)
  child.stdout.emit('data', Buffer.concat([header, body]))
}

async function loadBridge(): Promise<typeof import('./systemAudioMute')> {
  vi.resetModules()
  return import('./systemAudioMute')
}

beforeEach(() => {
  spawnMock.mockReset()
  captureMessageMock.mockReset()
})

describe('systemAudioMuteBridge — helper binary absent', () => {
  it('no-ops silently and stops re-spawning the missing exe', async () => {
    spawnMock.mockImplementation(() => {
      const child = makeChild(() => {})
      // Node reports a missing executable asynchronously, as an 'error' event.
      queueMicrotask(() =>
        child.emit('error', Object.assign(new Error('spawn ENOENT'), { code: 'ENOENT' }))
      )
      return child
    })
    const { systemAudioMuteBridge } = await loadBridge()

    // Neither call rejects — PTT proceeds exactly as if muting didn't exist.
    await expect(systemAudioMuteBridge.muteSystemAudio()).resolves.toBeUndefined()
    await expect(systemAudioMuteBridge.restoreSystemAudio()).resolves.toBeUndefined()
    await expect(systemAudioMuteBridge.muteSystemAudio()).resolves.toBeUndefined()

    // Only the first call tried to spawn; after ENOENT the bridge is latched
    // unavailable (otherwise every hold would re-spawn a missing exe and log).
    expect(spawnMock).toHaveBeenCalledTimes(1)

    // And the degrade is durable, not just a console line: exactly one Sentry
    // diagnostic (behind the unavailable guard) despite three mute/restore calls.
    expect(captureMessageMock).toHaveBeenCalledTimes(1)
    expect(captureMessageMock).toHaveBeenCalledWith(
      expect.stringContaining('win-audio-helper'),
      expect.objectContaining({ area: 'ptt-audio-mute', level: 'warning' })
    )
  })

  it('warm() is a no-op once the helper is known to be missing', async () => {
    spawnMock.mockImplementation(() => {
      const child = makeChild(() => {})
      queueMicrotask(() =>
        child.emit('error', Object.assign(new Error('spawn ENOENT'), { code: 'ENOENT' }))
      )
      return child
    })
    const { systemAudioMuteBridge } = await loadBridge()
    systemAudioMuteBridge.warm()
    await systemAudioMuteBridge.muteSystemAudio() // lets the ENOENT land
    systemAudioMuteBridge.warm()
    systemAudioMuteBridge.warm()
    expect(spawnMock).toHaveBeenCalledTimes(1)
  })
})

describe('systemAudioMuteBridge — live helper', () => {
  it('handshakes, then sends MUTE and RESTORE opcodes', async () => {
    const opcodes: number[] = []
    spawnMock.mockImplementation(() =>
      makeChild((opcode, _payload, child) => {
        opcodes.push(opcode)
        if (opcode === OP_HELLO) {
          reply(child, JSON.stringify({ ok: true, protocolVersion: PROTOCOL_VERSION }))
        } else {
          reply(child, JSON.stringify({ ok: true, muted: opcode === OP_MUTE }))
        }
      })
    )
    const { systemAudioMuteBridge } = await loadBridge()

    await systemAudioMuteBridge.muteSystemAudio()
    await systemAudioMuteBridge.restoreSystemAudio()

    expect(spawnMock).toHaveBeenCalledTimes(1) // one persistent child, not one per hold
    expect(opcodes).toEqual([OP_HELLO, OP_MUTE, OP_RESTORE])
  })

  it('swallows a helper-side error so a failed mute never breaks a hold', async () => {
    spawnMock.mockImplementation(() =>
      makeChild((opcode, _payload, child) => {
        if (opcode === OP_HELLO) {
          reply(child, JSON.stringify({ ok: true, protocolVersion: PROTOCOL_VERSION }))
          return
        }
        reply(child, JSON.stringify({ ok: false, message: 'no default device' }))
      })
    )
    const { systemAudioMuteBridge } = await loadBridge()
    await expect(systemAudioMuteBridge.muteSystemAudio()).resolves.toBeUndefined()
    await expect(systemAudioMuteBridge.restoreSystemAudio()).resolves.toBeUndefined()
  })

  it('DISABLES muting against a stale helper rather than driving it unsafely', async () => {
    // A pre-v3 helper neither unmutes on exit nor reports the device it muted, so
    // muting through it can strand the user's speakers with no way back. Refusing
    // to mute is the safe degradation; muting anyway is not.
    const opcodes: number[] = []
    spawnMock.mockImplementation(() =>
      makeChild((opcode, _payload, child) => {
        opcodes.push(opcode)
        if (opcode === OP_HELLO) reply(child, JSON.stringify({ ok: true, protocolVersion: 2 }))
        else reply(child, JSON.stringify({ ok: true, muted: true, deviceId: 'x' }))
      })
    )
    const { systemAudioMuteBridge } = await loadBridge()

    systemAudioMuteBridge.warm() // handshake fails the version check
    await vi.waitFor(() => expect(opcodes).toContain(OP_HELLO))

    await systemAudioMuteBridge.muteSystemAudio()
    expect(opcodes).not.toContain(OP_MUTE) // never muted through the stale helper
  })
})

// THE property of this feature: the endpoint mute is persistent OS state, so a
// helper that dies holding one leaves the user's speakers muted with the app gone.
// Every one of these is a "user is left muted" regression if it breaks.
describe('systemAudioMuteBridge — never leave the user muted', () => {
  const DEVICE = '{0.0.0.00000000}.{abc-123}'

  /** A helper that mutes DEVICE and answers the handshake. `onOp` observes ops. */
  function liveHelper(onOp?: (opcode: number, payload: string) => void) {
    return () =>
      makeChild((opcode, payload, child) => {
        onOp?.(opcode, payload)
        if (opcode === OP_HELLO) {
          reply(child, JSON.stringify({ ok: true, protocolVersion: PROTOCOL_VERSION }))
        } else if (opcode === OP_MUTE) {
          reply(child, JSON.stringify({ ok: true, muted: true, deviceId: DEVICE }))
        } else {
          reply(child, JSON.stringify({ ok: true, muted: false }))
        }
      })
  }

  it('restores with the deviceId of the mute it took, so a FRESH helper can undo it', async () => {
    const restorePayloads: string[] = []
    spawnMock.mockImplementation(
      liveHelper((opcode, payload) => {
        if (opcode === OP_RESTORE) restorePayloads.push(payload)
      })
    )
    const { systemAudioMuteBridge } = await loadBridge()

    await systemAudioMuteBridge.muteSystemAudio()
    await systemAudioMuteBridge.restoreSystemAudio()
    expect(JSON.parse(restorePayloads[0])).toEqual({ deviceId: DEVICE })

    // Once restored we hold nothing — a further restore must NOT claim a device
    // (a stale hint would unmute a device the user muted themselves later).
    await systemAudioMuteBridge.restoreSystemAudio()
    expect(JSON.parse(restorePayloads[1])).toEqual({})
  })

  it('re-spawns and replays RESTORE when the helper DIES while holding a mute', async () => {
    vi.useFakeTimers()
    try {
      const ops: Array<{ opcode: number; payload: string }> = []
      spawnMock.mockImplementation(liveHelper((opcode, payload) => ops.push({ opcode, payload })))
      const { systemAudioMuteBridge } = await loadBridge()

      await systemAudioMuteBridge.muteSystemAudio()
      const child = spawnMock.mock.results[0].value as FakeChild
      expect(spawnMock).toHaveBeenCalledTimes(1)

      // The helper is hard-killed mid-hold (crash / Task Manager). Its own
      // unmute-on-exit never runs — the mute is now stranded in the OS.
      ops.length = 0
      child.emit('exit', 1)

      await vi.advanceTimersByTimeAsync(2000) // recovery backoff
      await vi.waitFor(() => expect(spawnMock).toHaveBeenCalledTimes(2))

      // A replacement helper was spawned and told exactly which endpoint to unmute.
      const restore = ops.find((o) => o.opcode === OP_RESTORE)
      expect(
        restore,
        'expected a replayed RESTORE after the helper died holding a mute'
      ).toBeDefined()
      expect(JSON.parse(restore!.payload)).toEqual({ deviceId: DEVICE })
    } finally {
      vi.useRealTimers()
    }
  })

  it('does NOT re-spawn when the helper exits holding nothing', async () => {
    vi.useFakeTimers()
    try {
      spawnMock.mockImplementation(liveHelper())
      const { systemAudioMuteBridge } = await loadBridge()

      systemAudioMuteBridge.warm() // spawned, but no mute taken
      const child = spawnMock.mock.results[0].value as FakeChild
      child.emit('exit', 0)
      await vi.advanceTimersByTimeAsync(5000)

      expect(spawnMock).toHaveBeenCalledTimes(1) // nothing to heal ⇒ no respawn
    } finally {
      vi.useRealTimers()
    }
  })

  it('dispose() closes stdin (so the helper unmutes itself) instead of killing it', async () => {
    vi.useFakeTimers()
    try {
      spawnMock.mockImplementation(liveHelper())
      const { systemAudioMuteBridge } = await loadBridge()

      await systemAudioMuteBridge.muteSystemAudio()
      const child = spawnMock.mock.results[0].value as FakeChild

      systemAudioMuteBridge.dispose() // app quit, mid-hold
      // stdin EOF is the helper's cue to restore and exit; a TerminateProcess
      // would skip that and strand the mute.
      expect(child.stdinEnded).toBe(true)
      expect(child.killed).toBe(false)

      // And we must not resurrect a helper into a shutting-down app.
      await vi.advanceTimersByTimeAsync(5000)
      expect(spawnMock).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('hard-kills only a wedged helper that ignores the stdin close', async () => {
    vi.useFakeTimers()
    try {
      spawnMock.mockImplementation(liveHelper())
      const { systemAudioMuteBridge } = await loadBridge()
      systemAudioMuteBridge.warm()
      const child = spawnMock.mock.results[0].value as FakeChild

      systemAudioMuteBridge.dispose()
      expect(child.killed).toBe(false) // grace period first
      await vi.advanceTimersByTimeAsync(2000)
      expect(child.killed).toBe(true) // never exited ⇒ backstop kill
    } finally {
      vi.useRealTimers()
    }
  })
})
