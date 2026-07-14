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

type FakeChild = EventEmitter & {
  stdout: EventEmitter
  stderr: EventEmitter
  stdin: { write: (b: Buffer) => void }
  kill: () => void
}

function makeChild(onWrite: (opcode: number, child: FakeChild) => void): FakeChild {
  const child = new EventEmitter() as FakeChild
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  child.kill = () => {}
  child.stdin = { write: (frame: Buffer) => onWrite(frame.readUInt8(4), child) }
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
      makeChild((opcode, child) => {
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
      makeChild((opcode, child) => {
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
})
