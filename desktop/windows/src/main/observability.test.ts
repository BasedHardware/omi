import { mkdtempSync, readFileSync, rmSync } from 'fs'
import { existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { IpcMainEvent } from 'electron'

type IpcHandler = (event: IpcMainEvent, payload: unknown) => void

const mocks = vi.hoisted(() => {
  const ipcHandlers = new Map<string, IpcHandler>()
  return {
    app: {
      getPath: vi.fn(),
      on: vi.fn(),
      isPackaged: false
    },
    ipcHandlers,
    ipcMain: {
      on: vi.fn((channel: string, handler: IpcHandler) => {
        ipcHandlers.set(channel, handler)
      })
    }
  }
})

vi.mock('electron', () => ({
  app: mocks.app,
  ipcMain: mocks.ipcMain
}))

import {
  flushObservabilityWritesForTests,
  registerObservabilityIpc,
  resetObservabilityForTests
} from './observability'

function eventFor(url: string, id = 1): IpcMainEvent {
  return {
    senderFrame: { url },
    sender: {
      id,
      getURL: () => url
    }
  } as unknown as IpcMainEvent
}

function readLog(root: string): string {
  const file = join(root, 'observability.jsonl')
  return existsSync(file) ? readFileSync(file, 'utf8') : ''
}

describe('main observability IPC', () => {
  let root: string

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'omi-observability-'))
    resetObservabilityForTests()
    mocks.app.getPath.mockReturnValue(root)
    mocks.app.on.mockClear()
    mocks.ipcHandlers.clear()
    mocks.ipcMain.on.mockClear()
  })

  afterEach(() => {
    rmSync(root, { recursive: true, force: true })
  })

  it('accepts observability IPC only from trusted renderer origins', async () => {
    registerObservabilityIpc()
    const capture = mocks.ipcHandlers.get('observability:capture')
    expect(capture).toBeDefined()

    capture?.(eventFor('https://evil.example/app'), { name: 'evil.event', message: 'blocked' })
    capture?.(eventFor('file:///app/index.html'), { name: 'trusted.event', message: 'ok' })
    await flushObservabilityWritesForTests()

    const log = readLog(root)
    expect(log).not.toContain('evil.event')
    expect(log).toContain('trusted.event')
  })

  it('rate-limits renderer observability floods', async () => {
    registerObservabilityIpc()
    const capture = mocks.ipcHandlers.get('observability:capture')
    expect(capture).toBeDefined()

    for (let i = 0; i < 61; i += 1) {
      capture?.(eventFor('http://localhost:5173/index.html', 7), {
        name: `event.${i}`,
        message: 'ok'
      })
    }
    await flushObservabilityWritesForTests()

    const lines = readLog(root).trim().split('\n').filter(Boolean)
    expect(lines).toHaveLength(60)
    expect(readLog(root)).not.toContain('event.60')
  })

  it('replaces oversized events before writing them', async () => {
    registerObservabilityIpc()
    const capture = mocks.ipcHandlers.get('observability:capture')
    expect(capture).toBeDefined()
    const largeData = Object.fromEntries(
      Array.from({ length: 20_000 }, (_value, index) => [`key_${index}`, 'value'])
    )

    capture?.(eventFor('file:///app/index.html'), { name: 'large.event', data: largeData })
    await flushObservabilityWritesForTests()

    const log = readLog(root)
    expect(log).toContain('observability.event_too_large')
    expect(log).not.toContain('key_19999')
  })
})
