import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { RewindFrame } from '../../../shared/types'

const service = vi.hoisted(() => ({
  pipelineEnabled: true,
  transition: vi.fn(),
  leaveForExcludedContext: vi.fn(async () => {}),
  contextEntered: vi.fn(async () => {}),
  observe: vi.fn(),
  resolve: vi.fn((e: unknown) => e),
  runDepartureExtraction: vi.fn(async () => {}),
  recordTrackedFrame: vi.fn(),
  clearTrackedFrame: vi.fn(),
  wireDirectorSessionReset: vi.fn()
}))

vi.mock('./service', () => ({
  directorPipelineEnabled: () => service.pipelineEnabled,
  directorVisits: {
    transition: service.transition,
    leaveForExcludedContext: service.leaveForExcludedContext
  },
  directorEngine: { contextEntered: service.contextEntered },
  directorTcrs: { observe: service.observe },
  directorSubjectBinding: { resolve: service.resolve },
  runDepartureExtraction: service.runDepartureExtraction,
  recordTrackedFrame: service.recordTrackedFrame,
  clearTrackedFrame: service.clearTrackedFrame,
  wireDirectorSessionReset: service.wireDirectorSessionReset
}))

import { DirectorAssistant } from './directorAssistant'

const frame = (over: Partial<RewindFrame> = {}): RewindFrame =>
  ({
    id: 7,
    ts: 1_760_000_000_000,
    app: 'Code',
    windowTitle: 'main.ts',
    processName: 'Code.exe',
    ocrText: '',
    imagePath: 'C:/frames/7.jpg',
    width: 1920,
    height: 1080,
    indexed: 1,
    ...over
  }) as RewindFrame

beforeEach(() => {
  vi.clearAllMocks()
  service.pipelineEnabled = true
  service.transition.mockResolvedValue({
    departed: null,
    arriving: { visitID: 2, contextGeneration: 2, poolEpoch: 1, bucketID: 'b', startedAt: 0 }
  })
})

describe('DirectorAssistant routing', () => {
  it('pipeline on: a titled switch transitions and evaluates the arriving fence', async () => {
    const assistant = new DirectorAssistant()
    await assistant.onContextSwitch(frame(), 'Chrome', 'Inbox')
    expect(service.transition).toHaveBeenCalledWith(
      expect.objectContaining({ toApp: 'Chrome', toWindowTitle: 'Inbox', departingFrameId: 7 })
    )
    expect(service.contextEntered).toHaveBeenCalled()
    expect(service.runDepartureExtraction).not.toHaveBeenCalled()
    expect(service.observe).not.toHaveBeenCalled()
  })

  it('pipeline on: a completed departure also runs the extraction on the departing frame', async () => {
    const departedFence = {
      visitID: 1,
      contextGeneration: 1,
      poolEpoch: 1,
      bucketID: 'b',
      startedAt: 0
    }
    service.transition.mockResolvedValue({
      departed: { fence: departedFence, outcome: 'completed' },
      arriving: { visitID: 2, contextGeneration: 2, poolEpoch: 1, bucketID: 'b', startedAt: 0 }
    })
    const assistant = new DirectorAssistant()
    const departing = frame()
    await assistant.onContextSwitch(departing, 'Chrome', 'Inbox')
    expect(service.runDepartureExtraction).toHaveBeenCalledWith(departedFence, departing)
  })

  it('pipeline on: a privacy-denied arrival closes the visit and opens nothing', async () => {
    const assistant = new DirectorAssistant()
    await assistant.onContextSwitch(frame(), 'Chase Banking', null)
    expect(service.leaveForExcludedContext).toHaveBeenCalledWith(7)
    expect(service.transition).not.toHaveBeenCalled()
    expect(service.contextEntered).not.toHaveBeenCalled()
  })

  it('pipeline off: titled switches feed the TCRS producer through subject resolution', async () => {
    service.pipelineEnabled = false
    const assistant = new DirectorAssistant()
    await assistant.onContextSwitch(frame(), 'Chrome', 'Inbox')
    expect(service.transition).not.toHaveBeenCalled()
    expect(service.resolve).toHaveBeenCalledTimes(1)
    expect(service.observe).toHaveBeenCalledTimes(1)
    const observed = service.observe.mock.calls[0][0] as { kind: string; referenceHash: string }
    expect(observed.kind).toBe('app_window')
    expect(observed.referenceHash.startsWith('sha256:')).toBe(true)
  })

  it('pipeline off: privacy-denied arrivals produce no TCRS event', async () => {
    service.pipelineEnabled = false
    const assistant = new DirectorAssistant()
    await assistant.onContextSwitch(frame(), 'Chase Banking', null)
    expect(service.observe).not.toHaveBeenCalled()
  })

  it('analyze records the tracked frame; clearPendingWork drops it', async () => {
    const assistant = new DirectorAssistant()
    await assistant.analyze(frame())
    expect(service.recordTrackedFrame).toHaveBeenCalled()
    assistant.clearPendingWork()
    expect(service.clearTrackedFrame).toHaveBeenCalled()
  })
})
