// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  startContextProjectionHost,
  _resetContextProjectionHostForTests
} from './contextProjectionHost'
import { dashboardIntelligence } from './dashboardStore'

vi.mock('../clientDevice', () => ({ getWindowsDeviceIdHash: async () => 'abcd1234' }))

const wireProjection = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  schema_version: 1,
  evaluation_id: 'evaluation_1',
  output_version: 'output_1',
  material_version: 'material_1',
  generated_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 60_000).toISOString(),
  recommendations: [],
  ...over
})

let projectionListener: ((raw: unknown) => void) | null = null
let setDeviceId: ReturnType<typeof vi.fn>

beforeEach(() => {
  _resetContextProjectionHostForTests()
  projectionListener = null
  setDeviceId = vi.fn()
  ;(window as unknown as { omi: Record<string, unknown> }).omi = {
    directorSetDeviceId: setDeviceId,
    onContextProjection: (cb: (raw: unknown) => void) => {
      projectionListener = cb
      return () => {
        projectionListener = null
      }
    }
  }
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('startContextProjectionHost', () => {
  it('relays the device-id hash and applies valid projections once loaded', async () => {
    vi.spyOn(dashboardIntelligence, 'getState').mockReturnValue({
      hasLoadedOnce: true,
      accountGeneration: 3
    } as ReturnType<typeof dashboardIntelligence.getState>)
    const apply = vi
      .spyOn(dashboardIntelligence, 'applyContextProjection')
      .mockImplementation(() => {})

    startContextProjectionHost()
    await Promise.resolve()
    await Promise.resolve()
    expect(setDeviceId).toHaveBeenCalledWith('abcd1234')

    projectionListener?.(wireProjection())
    expect(apply).toHaveBeenCalledTimes(1)
    expect(apply.mock.calls[0][0].evaluationId).toBe('evaluation_1')
  })

  it('drops malformed payloads and projections before the first load', () => {
    const getState = vi
      .spyOn(dashboardIntelligence, 'getState')
      .mockReturnValue({ hasLoadedOnce: false, accountGeneration: null } as ReturnType<
        typeof dashboardIntelligence.getState
      >)
    const apply = vi
      .spyOn(dashboardIntelligence, 'applyContextProjection')
      .mockImplementation(() => {})

    startContextProjectionHost()
    projectionListener?.({ not: 'a projection' })
    expect(apply).not.toHaveBeenCalled()

    projectionListener?.(wireProjection())
    expect(apply).not.toHaveBeenCalled()

    // Loaded but out-of-rollout (generation null) still rejects.
    getState.mockReturnValue({ hasLoadedOnce: true, accountGeneration: null } as ReturnType<
      typeof dashboardIntelligence.getState
    >)
    projectionListener?.(wireProjection())
    expect(apply).not.toHaveBeenCalled()

    getState.mockReturnValue({ hasLoadedOnce: true, accountGeneration: 3 } as ReturnType<
      typeof dashboardIntelligence.getState
    >)
    projectionListener?.(wireProjection())
    expect(apply).toHaveBeenCalledTimes(1)
  })

  it('starts once: a second call never double-subscribes', () => {
    const subscribe = vi.fn(() => () => {})
    ;(window as unknown as { omi: Record<string, unknown> }).omi = {
      directorSetDeviceId: setDeviceId,
      onContextProjection: subscribe
    }
    startContextProjectionHost()
    startContextProjectionHost()
    expect(subscribe).toHaveBeenCalledTimes(1)
  })
})
