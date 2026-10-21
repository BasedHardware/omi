import { describe, it, expect, beforeEach, vi } from 'vitest'

const getSources = vi.fn()
const getPrimaryDisplay = vi.fn()
const getDisplayMatching = vi.fn()
const screenToDipRect = vi.fn()
const getCursorScreenPoint = vi.fn()
const getDisplayNearestPoint = vi.fn()
const getForegroundWindowRect = vi.fn()
const on = vi.fn()

vi.mock('electron', () => ({
  desktopCapturer: { getSources: (...args: unknown[]) => getSources(...args) },
  screen: {
    getPrimaryDisplay: () => getPrimaryDisplay(),
    getDisplayMatching: (...args: unknown[]) => getDisplayMatching(...args),
    screenToDipRect: (...args: unknown[]) => screenToDipRect(...args),
    getCursorScreenPoint: () => getCursorScreenPoint(),
    getDisplayNearestPoint: (...args: unknown[]) => getDisplayNearestPoint(...args),
    on: (...args: unknown[]) => on(...args)
  }
}))

vi.mock('../usage/nativeForeground', () => ({
  getForegroundWindowRect: () => getForegroundWindowRect()
}))

// The module caches at module scope, so each test gets a fresh copy.
async function loadModule(): Promise<typeof import('./sourceId')> {
  vi.resetModules()
  return import('./sourceId')
}

const source = (id: string, displayId: string): { id: string; display_id: string } => ({
  id,
  display_id: displayId
})

describe('getPrimarySourceId', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPrimaryDisplay.mockReturnValue({ id: 2 })
  })

  it('picks the source whose display_id is the primary display, not the first one', async () => {
    getSources.mockResolvedValue([source('screen:1:0', '1'), source('screen:0:0', '2')])
    const { getPrimarySourceId } = await loadModule()
    expect(await getPrimarySourceId()).toBe('screen:0:0')
  })

  it('falls back to the first source when no display_id matches', async () => {
    getSources.mockResolvedValue([source('screen:1:0', '7'), source('screen:0:0', '8')])
    const { getPrimarySourceId } = await loadModule()
    expect(await getPrimarySourceId()).toBe('screen:1:0')
  })

  it('falls back to the first source when Electron reports no display ids', async () => {
    getSources.mockResolvedValue([source('screen:1:0', ''), source('screen:0:0', '')])
    const { getPrimarySourceId } = await loadModule()
    expect(await getPrimarySourceId()).toBe('screen:1:0')
  })

  it('returns null when there are no screen sources', async () => {
    getSources.mockResolvedValue([])
    const { getPrimarySourceId } = await loadModule()
    expect(await getPrimarySourceId()).toBeNull()
  })

  it('caches the id and dedupes concurrent callers into one getSources() call', async () => {
    getSources.mockResolvedValue([source('screen:0:0', '2')])
    const { getPrimarySourceId } = await loadModule()

    const [a, b] = await Promise.all([getPrimarySourceId(), getPrimarySourceId()])
    const c = await getPrimarySourceId()

    expect([a, b, c]).toEqual(['screen:0:0', 'screen:0:0', 'screen:0:0'])
    expect(getSources).toHaveBeenCalledTimes(1)
  })
})

describe('getRewindCaptureDiagnostics — desktopCapturer failure classification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPrimaryDisplay.mockReturnValue({ id: 2 })
    getForegroundWindowRect.mockReturnValue({ rect: null, className: null, exePath: null })
    getCursorScreenPoint.mockReturnValue({ x: 0, y: 0 })
    getDisplayNearestPoint.mockReturnValue({ id: 2 })
  })

  it('reports available with no reason when sources resolve normally', async () => {
    getSources.mockResolvedValue([source('screen:0:0', '2')])
    const { getRewindCaptureDiagnostics } = await loadModule()

    expect(await getRewindCaptureDiagnostics()).toEqual({
      available: true,
      reason: null,
      likelyMissingLinuxPortal: false
    })
  })

  it('does NOT throw/reject when desktopCapturer.getSources() fails — resolves to unavailable instead', async () => {
    // Live bug: this used to reject out of the 'rewind:captureSourceId' IPC
    // handler uncaught, and Rewind just never started with no UI signal at all.
    getSources.mockRejectedValue(new Error('Failed to get sources.'))
    const { getPrimarySourceId, getRewindCaptureSourceId, getRewindCaptureDiagnostics } =
      await loadModule()

    await expect(getPrimarySourceId()).resolves.toBeNull()
    await expect(getRewindCaptureSourceId()).resolves.toBeNull()
    expect(await getRewindCaptureDiagnostics()).toEqual({
      available: false,
      reason: 'Failed to get sources.',
      likelyMissingLinuxPortal: process.platform === 'linux'
    })
  })

  it('flags likelyMissingLinuxPortal only on linux', async () => {
    getSources.mockRejectedValue(new Error('Failed to get sources.'))
    const { getRewindCaptureDiagnostics } = await loadModule()
    const original = process.platform
    Object.defineProperty(process, 'platform', { value: 'linux' })
    try {
      expect((await getRewindCaptureDiagnostics()).likelyMissingLinuxPortal).toBe(true)
    } finally {
      Object.defineProperty(process, 'platform', { value: original })
    }
  })

  it('does not flag likelyMissingLinuxPortal on win32', async () => {
    getSources.mockRejectedValue(new Error('Failed to get sources.'))
    const { getRewindCaptureDiagnostics } = await loadModule()
    const original = process.platform
    Object.defineProperty(process, 'platform', { value: 'win32' })
    try {
      expect((await getRewindCaptureDiagnostics()).likelyMissingLinuxPortal).toBe(false)
    } finally {
      Object.defineProperty(process, 'platform', { value: original })
    }
  })
})

describe('prewarmPrimarySourceId', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPrimaryDisplay.mockReturnValue({ id: 2 })
  })

  it('re-resolves the primary source after the display layout changes', async () => {
    getSources.mockResolvedValue([source('screen:0:0', '2')])
    const { prewarmPrimarySourceId, getPrimarySourceId } = await loadModule()

    prewarmPrimarySourceId()
    expect(await getPrimarySourceId()).toBe('screen:0:0')

    // The user makes the other monitor primary: same sources, new primary display.
    getSources.mockResolvedValue([source('screen:0:0', '2'), source('screen:1:0', '3')])
    getPrimaryDisplay.mockReturnValue({ id: 3 })

    const invalidate = on.mock.calls.find(([event]) => event === 'display-metrics-changed')?.[1] as
      | (() => void)
      | undefined
    expect(invalidate).toBeTypeOf('function')
    invalidate?.()

    expect(await getPrimarySourceId()).toBe('screen:1:0')
  })
})

describe('getRewindCaptureSourceId', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPrimaryDisplay.mockReturnValue({ id: 2 })
    getForegroundWindowRect.mockReturnValue({
      rect: null,
      className: null,
      exePath: null
    })
    getCursorScreenPoint.mockReturnValue({ x: 100, y: 100 })
    getDisplayNearestPoint.mockReturnValue({ id: 2 })
    screenToDipRect.mockImplementation((_window, rect) => rect)
    getDisplayMatching.mockReturnValue({ id: 2 })
  })

  it('selects the source for the display containing the foreground window', async () => {
    const physicalRect = { x: 3840, y: 0, width: 1920, height: 1080 }
    const dipRect = { x: 2560, y: 0, width: 1280, height: 720 }
    getForegroundWindowRect.mockReturnValue({
      rect: physicalRect,
      className: 'Chrome_WidgetWin_1',
      exePath: 'C:\\Chrome\\chrome.exe'
    })
    screenToDipRect.mockReturnValue(dipRect)
    getDisplayMatching.mockReturnValue({ id: 3 })
    getSources.mockResolvedValue([source('screen:0:0', '2'), source('screen:1:0', '3')])

    const { getRewindCaptureSourceId } = await loadModule()

    expect(await getRewindCaptureSourceId()).toBe('screen:1:0')
    expect(screenToDipRect).toHaveBeenCalledWith(null, physicalRect)
    expect(getDisplayMatching).toHaveBeenCalledWith(dipRect)
  })

  it('uses the cursor display when foreground geometry is unavailable', async () => {
    getDisplayNearestPoint.mockReturnValue({ id: 3 })
    getSources.mockResolvedValue([source('screen:0:0', '2'), source('screen:1:0', '3')])

    const { getRewindCaptureSourceId } = await loadModule()

    expect(await getRewindCaptureSourceId()).toBe('screen:1:0')
  })

  it('reuses the source map while the foreground window moves between displays', async () => {
    getForegroundWindowRect.mockReturnValue({
      rect: { x: 0, y: 0, width: 100, height: 100 },
      className: 'TestWindow',
      exePath: 'C:\\test.exe'
    })
    getDisplayMatching.mockReturnValueOnce({ id: 2 }).mockReturnValueOnce({ id: 3 })
    getSources.mockResolvedValue([source('screen:0:0', '2'), source('screen:1:0', '3')])

    const { getRewindCaptureSourceId } = await loadModule()

    expect(await getRewindCaptureSourceId()).toBe('screen:0:0')
    expect(await getRewindCaptureSourceId()).toBe('screen:1:0')
    expect(getSources).toHaveBeenCalledTimes(1)
  })

  it('falls back to the primary source when the target display has no source', async () => {
    getDisplayNearestPoint.mockReturnValue({ id: 99 })
    getSources.mockResolvedValue([source('screen:0:0', '2'), source('screen:1:0', '3')])

    const { getRewindCaptureSourceId } = await loadModule()

    expect(await getRewindCaptureSourceId()).toBe('screen:0:0')
  })

  it('rejects a frame captured from a display that is no longer foreground', async () => {
    getDisplayNearestPoint.mockReturnValue({ id: 3 })
    getSources.mockResolvedValue([source('screen:0:0', '2'), source('screen:1:0', '3')])

    const { isCurrentRewindCaptureSource } = await loadModule()

    expect(await isCurrentRewindCaptureSource('screen:0:0')).toBe(false)
    expect(await isCurrentRewindCaptureSource('screen:1:0')).toBe(true)
    expect(await isCurrentRewindCaptureSource('')).toBe(false)
  })
})
