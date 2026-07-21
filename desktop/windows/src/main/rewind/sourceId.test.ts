import { describe, it, expect, beforeEach, vi } from 'vitest'

const getSources = vi.fn()
const getPrimaryDisplay = vi.fn()
const on = vi.fn()

vi.mock('electron', () => ({
  desktopCapturer: { getSources: (...args: unknown[]) => getSources(...args) },
  screen: {
    getPrimaryDisplay: () => getPrimaryDisplay(),
    on: (...args: unknown[]) => on(...args)
  }
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
      (() => void) | undefined
    expect(invalidate).toBeTypeOf('function')
    invalidate?.()

    expect(await getPrimarySourceId()).toBe('screen:1:0')
  })
})
