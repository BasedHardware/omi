import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type MockWindow = {
  destroyed: boolean
  isDestroyed: () => boolean
  webContents: { send: ReturnType<typeof vi.fn> }
}

const windows: MockWindow[] = []
const subscriptions: Array<() => void> = []
const unsubscribes: Array<ReturnType<typeof vi.fn>> = []

vi.mock('electron', () => ({
  BrowserWindow: {
    getAllWindows: () => windows
  }
}))

vi.mock('../usage/nativeForeground', () => ({
  subscribeForegroundChange: vi.fn((cb: () => void) => {
    const unsubscribe = vi.fn()
    subscriptions.push(cb)
    unsubscribes.push(unsubscribe)
    return unsubscribe
  })
}))

import { subscribeForegroundChange } from '../usage/nativeForeground'
import {
  notifyRewindCaptureNow,
  startRewindForegroundCaptureTrigger,
  stopRewindForegroundCaptureTrigger
} from './foregroundCaptureTrigger'

const platformDescriptor = Object.getOwnPropertyDescriptor(process, 'platform')

function makeWindow(destroyed = false): MockWindow {
  return {
    destroyed,
    isDestroyed(): boolean {
      return this.destroyed
    },
    webContents: { send: vi.fn() }
  }
}

function forcePlatform(platform: NodeJS.Platform): void {
  Object.defineProperty(process, 'platform', { value: platform })
}

describe('rewind foreground capture trigger', () => {
  beforeEach(() => {
    stopRewindForegroundCaptureTrigger()
    windows.length = 0
    subscriptions.length = 0
    unsubscribes.length = 0
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.setSystemTime(1000)
    forcePlatform('win32')
  })

  afterEach(() => {
    stopRewindForegroundCaptureTrigger()
    vi.useRealTimers()
    if (platformDescriptor) Object.defineProperty(process, 'platform', platformDescriptor)
  })

  it('broadcasts capture requests to live windows only', () => {
    const live = makeWindow()
    const destroyed = makeWindow(true)
    windows.push(live, destroyed)

    notifyRewindCaptureNow()

    expect(live.webContents.send).toHaveBeenCalledWith('rewind:captureNow')
    expect(destroyed.webContents.send).not.toHaveBeenCalled()
  })

  it('subscribes once and throttles foreground-change bursts', () => {
    const live = makeWindow()
    windows.push(live)

    startRewindForegroundCaptureTrigger()
    startRewindForegroundCaptureTrigger()

    expect(subscribeForegroundChange).toHaveBeenCalledTimes(1)
    expect(subscriptions).toHaveLength(1)

    subscriptions[0]()
    expect(live.webContents.send).toHaveBeenCalledTimes(1)

    vi.setSystemTime(1100)
    subscriptions[0]()
    expect(live.webContents.send).toHaveBeenCalledTimes(1)

    vi.setSystemTime(1300)
    subscriptions[0]()
    expect(live.webContents.send).toHaveBeenCalledTimes(2)
  })

  it('unsubscribes on stop', () => {
    startRewindForegroundCaptureTrigger()

    stopRewindForegroundCaptureTrigger()

    expect(unsubscribes[0]).toHaveBeenCalledTimes(1)
  })

  it('does not subscribe off Windows', () => {
    forcePlatform('darwin')

    startRewindForegroundCaptureTrigger()

    expect(subscribeForegroundChange).not.toHaveBeenCalled()
  })
})
