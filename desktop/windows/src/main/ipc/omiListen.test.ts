import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ListenMessage, ListenStartArgs, LocalSttStatus } from '../../shared/types'

const hoisted = vi.hoisted(() => {
  const wsInstances: Array<{ url: string }> = []

  class MockWebSocket {
    static OPEN = 1
    url: string
    binaryType = ''
    readyState = 0
    handlers = new Map<string, (...args: unknown[]) => void>()

    constructor(url: string) {
      this.url = url
      wsInstances.push(this)
    }

    on(event: string, handler: (...args: unknown[]) => void): void {
      this.handlers.set(event, handler)
    }

    close(): void {
      /* noop */
    }

    send(): void {
      /* noop */
    }
  }

  return {
    MockWebSocket,
    wsInstances,
    handleRegistrations: new Map<string, (...args: unknown[]) => unknown>(),
    sentMessages: [] as ListenMessage[],
    ensureManagedParakeetRuntime: vi.fn(),
    getLocalSttStatus: vi.fn(),
    sessionInstances: [] as Array<{ start: ReturnType<typeof vi.fn> }>
  }
})

vi.mock('electron', () => ({
  ipcMain: {
    handle: vi.fn((channel: string, handler: (...args: unknown[]) => unknown) => {
      hoisted.handleRegistrations.set(channel, handler)
    }),
    on: vi.fn()
  },
  webContents: {
    fromId: vi.fn(() => ({
      isDestroyed: () => false,
      send: (_channel: string, msg: ListenMessage) => {
        hoisted.sentMessages.push(msg)
      }
    }))
  }
}))

vi.mock('ws', () => ({ default: hoisted.MockWebSocket }))

vi.mock('../localStt/status', () => ({
  getLocalSttStatus: hoisted.getLocalSttStatus
}))

vi.mock('../localStt/parakeetCppRuntime', () => ({
  ensureManagedParakeetRuntime: hoisted.ensureManagedParakeetRuntime
}))

vi.mock('../localStt/parakeetCppSession', () => ({
  ParakeetCppSession: class {
    start = vi.fn(async () => undefined)
    stop = vi.fn(async () => undefined)
    feed = vi.fn()

    constructor() {
      hoisted.sessionInstances.push(this as unknown as { start: ReturnType<typeof vi.fn> })
    }
  }
}))

import { registerOmiListenHandlers } from './omiListen'

function sttStatus(overrides: {
  available: boolean
  canInstall: boolean
  reason?: string
}): LocalSttStatus {
  return {
    backend: 'parakeet',
    healthy: overrides.available,
    available: overrides.available,
    nvidiaAvailable: true,
    managed: true,
    runtime: {
      kind: 'parakeet.cpp',
      installState: overrides.available ? 'installed' : 'not_installed',
      variant: 'cuda',
      model: 'tdt_ctc-110m-q8_0.gguf',
      canInstall: overrides.canInstall
    },
    reason: overrides.reason,
    checkedAt: 1
  }
}

let nextSession = 1

function startArgs(sttMode: ListenStartArgs['sttMode']): ListenStartArgs {
  return {
    sessionId: `test-session-${nextSession++}`,
    source: 'mic',
    token: 'not.a.jwt',
    language: 'en',
    sttMode
  }
}

async function invokeStart(args: ListenStartArgs): Promise<void> {
  const handler = hoisted.handleRegistrations.get('omi-listen:start')
  if (!handler) throw new Error('omi-listen:start handler not registered')
  await handler({ sender: { id: 1 } }, args)
}

registerOmiListenHandlers()

beforeEach(() => {
  hoisted.wsInstances.length = 0
  hoisted.sentMessages.length = 0
  hoisted.sessionInstances.length = 0
  hoisted.ensureManagedParakeetRuntime.mockReset()
  hoisted.getLocalSttStatus.mockReset()
})

describe('omi-listen start routing', () => {
  it('auto with an installable-but-not-installed runtime goes straight to cloud without installing', async () => {
    hoisted.getLocalSttStatus.mockResolvedValue(sttStatus({ available: false, canInstall: true }))

    await invokeStart(startArgs('auto'))

    expect(hoisted.ensureManagedParakeetRuntime).not.toHaveBeenCalled()
    expect(hoisted.sessionInstances).toHaveLength(0)
    expect(hoisted.wsInstances).toHaveLength(1)
    expect(hoisted.wsInstances[0].url).toContain('/v4/listen')
    expect(hoisted.sentMessages.map((m) => m.kind)).not.toContain('error')
    const events = hoisted.sentMessages.filter((m) => m.kind === 'event')
    expect(events).toHaveLength(0)
  })

  it('missing sttMode defaults to auto and stays on cloud when the runtime is only installable', async () => {
    hoisted.getLocalSttStatus.mockResolvedValue(sttStatus({ available: false, canInstall: true }))

    await invokeStart(startArgs(undefined))

    expect(hoisted.ensureManagedParakeetRuntime).not.toHaveBeenCalled()
    expect(hoisted.wsInstances).toHaveLength(1)
  })

  it('explicit local-parakeet mode may install the runtime on first use', async () => {
    hoisted.getLocalSttStatus.mockResolvedValue(sttStatus({ available: false, canInstall: true }))
    hoisted.ensureManagedParakeetRuntime.mockResolvedValue({
      exePath: 'C:/runtime/bin/parakeet-cli.exe',
      modelPath: 'C:/runtime/models/tdt.gguf',
      runtimeRoot: 'C:/runtime',
      variant: 'cuda',
      model: 'tdt.gguf',
      version: 'v0.3.2'
    })

    await invokeStart(startArgs('local-parakeet'))

    expect(hoisted.ensureManagedParakeetRuntime).toHaveBeenCalledWith({}, { allowInstall: true })
    expect(hoisted.sessionInstances.length).toBeGreaterThan(0)
    expect(hoisted.wsInstances).toHaveLength(0)
    const events = hoisted.sentMessages.filter((m) => m.kind === 'event')
    expect(events.map((m) => (m.kind === 'event' ? m.event.type : ''))).toContain(
      'local_stt_installing'
    )
  })

  it('auto with an installed runtime uses local STT without permitting installs', async () => {
    hoisted.getLocalSttStatus.mockResolvedValue(sttStatus({ available: true, canInstall: true }))
    hoisted.ensureManagedParakeetRuntime.mockResolvedValue({
      exePath: 'C:/runtime/bin/parakeet-cli.exe',
      modelPath: 'C:/runtime/models/tdt.gguf',
      runtimeRoot: 'C:/runtime',
      variant: 'cuda',
      model: 'tdt.gguf',
      version: 'v0.3.2'
    })

    await invokeStart(startArgs('auto'))

    expect(hoisted.ensureManagedParakeetRuntime).toHaveBeenCalledWith({}, { allowInstall: false })
    expect(hoisted.sessionInstances.length).toBeGreaterThan(0)
    expect(hoisted.wsInstances).toHaveLength(0)
  })

  it('explicit local-parakeet mode fails fatally when the runtime is unsupported', async () => {
    hoisted.getLocalSttStatus.mockResolvedValue(
      sttStatus({ available: false, canInstall: false, reason: 'NVIDIA GPU not detected' })
    )

    await invokeStart(startArgs('local-parakeet'))

    expect(hoisted.ensureManagedParakeetRuntime).not.toHaveBeenCalled()
    expect(hoisted.wsInstances).toHaveLength(0)
    const errors = hoisted.sentMessages.filter((m) => m.kind === 'error')
    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatchObject({ message: 'NVIDIA GPU not detected', fatal: true })
  })
})
