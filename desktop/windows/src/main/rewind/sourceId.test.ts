import { beforeEach, describe, expect, it, vi } from 'vitest'

const electron = vi.hoisted(() => ({
  getSources: vi.fn(),
  getPrimaryDisplay: vi.fn(),
  on: vi.fn()
}))

vi.mock('electron', () => ({
  desktopCapturer: { getSources: electron.getSources },
  screen: {
    getPrimaryDisplay: electron.getPrimaryDisplay,
    on: electron.on
  }
}))

async function loadSourceId(): Promise<typeof import('./sourceId')> {
  vi.resetModules()
  return import('./sourceId')
}

describe('getPrimarySourceId', () => {
  beforeEach(() => {
    electron.getSources.mockReset()
    electron.getPrimaryDisplay.mockReset()
    electron.on.mockReset()
    electron.getPrimaryDisplay.mockReturnValue({ id: 202 })
  })

  it('selects the source whose display ID matches the primary display', async () => {
    electron.getSources.mockResolvedValue([
      { id: 'screen:0:0', display_id: '101' },
      { id: 'screen:1:0', display_id: '202' }
    ])

    const { getPrimarySourceId } = await loadSourceId()

    await expect(getPrimarySourceId()).resolves.toBe('screen:1:0')
    expect(electron.getPrimaryDisplay).toHaveBeenCalledOnce()
  })

  it('falls back to the first source when Electron exposes no matching display ID', async () => {
    electron.getSources.mockResolvedValue([
      { id: 'screen:0:0', display_id: '' },
      { id: 'screen:1:0', display_id: '' }
    ])

    const { getPrimarySourceId } = await loadSourceId()

    await expect(getPrimarySourceId()).resolves.toBe('screen:0:0')
  })

  it('returns null when no screen source is available', async () => {
    electron.getSources.mockResolvedValue([])

    const { getPrimarySourceId } = await loadSourceId()

    await expect(getPrimarySourceId()).resolves.toBeNull()
  })

  it('caches the selected source for the session', async () => {
    electron.getSources.mockResolvedValue([{ id: 'screen:1:0', display_id: '202' }])

    const { getPrimarySourceId } = await loadSourceId()

    await expect(getPrimarySourceId()).resolves.toBe('screen:1:0')
    await expect(getPrimarySourceId()).resolves.toBe('screen:1:0')
    expect(electron.getSources).toHaveBeenCalledOnce()
  })

  it('selects again after display metrics invalidate the cache', async () => {
    const listeners = new Map<string, () => void>()
    electron.on.mockImplementation((event: string, listener: () => void) => {
      listeners.set(event, listener)
    })
    electron.getSources
      .mockResolvedValueOnce([{ id: 'screen:0:0', display_id: '202' }])
      .mockResolvedValueOnce([{ id: 'screen:1:0', display_id: '303' }])

    const { getPrimarySourceId, prewarmPrimarySourceId } = await loadSourceId()
    prewarmPrimarySourceId()
    await expect(getPrimarySourceId()).resolves.toBe('screen:0:0')

    electron.getPrimaryDisplay.mockReturnValue({ id: 303 })
    listeners.get('display-metrics-changed')?.()

    await expect(getPrimarySourceId()).resolves.toBe('screen:1:0')
    expect(electron.getSources).toHaveBeenCalledTimes(2)
  })
})
