import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  generate: vi.fn(),
  omiApiPost: vi.fn(),
  maybeBuildLocalGraph: vi.fn()
}))

vi.mock('./geminiClient', () => ({ generate: h.generate }))
vi.mock('./apiClient', () => ({ omiApi: { post: h.omiApiPost } }))
vi.mock('./kgSynthesis', () => ({ maybeBuildLocalGraph: h.maybeBuildLocalGraph }))

import { runScreenSynthesisOnce } from './screenSynthesis'
import { GeminiLane } from '../../../shared/geminiAttribution'

const g = globalThis as { window?: { omi?: Record<string, unknown> } }

function stubBridge(over: Record<string, unknown> = {}): void {
  g.window = {
    omi: {
      screenSynthGetState: async () => ({
        enabled: true,
        watermarkTs: 0,
        lastRunAt: null,
        lastCount: 0,
        denylist: []
      }),
      screenSynthFramesSince: async () => [
        { ts: 1, app: 'Code', windowTitle: 'editor', processName: 'code', ocrText: 'func main' }
      ],
      screenSynthAdvanceWatermark: vi.fn(async () => {}),
      screenSynthRecordRun: vi.fn(async () => {}),
      ...over
    }
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  h.generate.mockResolvedValue('[]')
  stubBridge()
})

describe('runScreenSynthesisOnce — attribution', () => {
  it('calls generate with the screenSynthesis lane and extraction workload', async () => {
    await runScreenSynthesisOnce()
    expect(h.generate).toHaveBeenCalledTimes(1)
    expect(h.generate.mock.calls[0][0]).toMatchObject({
      model: 'gemini-2.5-flash',
      lane: GeminiLane.screenSynthesis,
      workload: 'extraction'
    })
  })

  it('does not call generate when synthesis is disabled', async () => {
    stubBridge({
      screenSynthGetState: async () => ({
        enabled: false,
        watermarkTs: 0,
        lastRunAt: null,
        lastCount: 0,
        denylist: []
      })
    })
    await runScreenSynthesisOnce()
    expect(h.generate).not.toHaveBeenCalled()
  })
})
