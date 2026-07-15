// The assistant's wiring: the master AND-gate, the excluded-app skip, the
// confidence gate, the recent-memories dedup threading, and the interval cadence.
// The pure decision modules (models, prompt) are tested separately; here every
// impure collaborator is mocked and we assert the assistant calls them correctly.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MemoryExtractionResult } from './models'
import type { MemoryToPersist } from './persist'

const h = vi.hoisted(() => ({
  settings: {
    memoryEnabled: true,
    memoryExtractionIntervalMin: 10,
    memoryMinConfidence: 0.7,
    memoryExcludedApps: [] as string[]
  },
  notificationsActive: vi.fn(() => true),
  readFrameImageBase64: vi.fn(async (): Promise<string | null> => 'BASE64'),
  getBackendSession: vi.fn(
    (): { apiBase: string; desktopApiBase: string; token: string } | null => ({
      apiBase: 'a',
      desktopApiBase: 'd',
      token: 't'
    })
  ),
  recentMemories: vi.fn((): { content: string; category: string }[] => []),
  extractMemory: vi.fn(),
  persistMemory: vi.fn((_mem: MemoryToPersist, _epoch: number): number | null => 1)
}))

vi.mock('../../appSettings', () => ({ getAppSettings: () => h.settings }))
vi.mock('../core/notify', () => ({ notificationsActive: h.notificationsActive }))
vi.mock('../core/frameImage', () => ({ readFrameImageBase64: h.readFrameImageBase64 }))
vi.mock('../core/session', () => ({
  getBackendSession: h.getBackendSession,
  getSessionEpoch: () => 1
}))
vi.mock('../../ipc/db', () => ({ recentMemories: h.recentMemories }))
vi.mock('./gemini', () => ({ extractMemory: h.extractMemory }))
vi.mock('./persist', () => ({ persistMemory: h.persistMemory }))

import { MemoryAssistant } from './memoryAssistant'
import type { RewindFrame } from '../../../shared/types'

function frame(over: Partial<RewindFrame> = {}): RewindFrame {
  return {
    id: 1,
    ts: 1000,
    app: 'Slack',
    windowTitle: 'general',
    processName: 'slack',
    ocrText: '',
    imagePath: 'C:/x.jpg',
    width: 100,
    height: 100,
    indexed: 0,
    ...over
  }
}

function result(over: Partial<MemoryExtractionResult> = {}): MemoryExtractionResult {
  return {
    hasNewMemory: true,
    memories: [
      { content: 'User works at Acme', category: 'system', sourceApp: 'Slack', confidence: 0.9 }
    ],
    contextSummary: 'a workspace',
    currentActivity: 'reading',
    ...over
  }
}

beforeEach(() => {
  h.settings.memoryEnabled = true
  h.settings.memoryExtractionIntervalMin = 10
  h.settings.memoryMinConfidence = 0.7
  h.settings.memoryExcludedApps = []
  vi.clearAllMocks()
  h.notificationsActive.mockReturnValue(true)
  h.readFrameImageBase64.mockResolvedValue('BASE64')
  h.getBackendSession.mockReturnValue({ apiBase: 'a', desktopApiBase: 'd', token: 't' })
  h.recentMemories.mockReturnValue([])
  h.persistMemory.mockReturnValue(1)
})

afterEach(() => vi.restoreAllMocks())

describe('isEnabled — the master AND-gate', () => {
  it('is true only when BOTH memoryEnabled and notificationsActive are on', () => {
    const a = new MemoryAssistant()
    expect(a.isEnabled()).toBe(true)

    h.notificationsActive.mockReturnValue(false)
    expect(a.isEnabled()).toBe(false) // no deliverable notification → no Gemini spend

    h.notificationsActive.mockReturnValue(true)
    h.settings.memoryEnabled = false
    expect(a.isEnabled()).toBe(false)
  })

  it('is false after stop()', () => {
    const a = new MemoryAssistant()
    a.stop()
    expect(a.isEnabled()).toBe(false)
  })
})

describe('shouldAnalyze — the fixed extraction interval', () => {
  it('runs only once the interval has elapsed (10 min default → 600000 ms)', () => {
    const a = new MemoryAssistant()
    expect(a.shouldAnalyze(0, 599_999)).toBe(false)
    expect(a.shouldAnalyze(0, 600_000)).toBe(true)
  })

  it('honours a custom interval from settings', () => {
    h.settings.memoryExtractionIntervalMin = 3
    const a = new MemoryAssistant()
    expect(a.shouldAnalyze(0, 179_999)).toBe(false)
    expect(a.shouldAnalyze(0, 180_000)).toBe(true)
  })
})

describe('analyze — local gates', () => {
  it('skips an excluded app without calling Gemini', async () => {
    h.settings.memoryExcludedApps = ['slack']
    const a = new MemoryAssistant()
    await a.analyze(frame({ app: 'Slack', processName: 'slack' }))
    expect(h.extractMemory).not.toHaveBeenCalled()
  })

  it('does not call Gemini with no backend session', async () => {
    h.getBackendSession.mockReturnValue(null)
    const a = new MemoryAssistant()
    await a.analyze(frame())
    expect(h.extractMemory).not.toHaveBeenCalled()
  })

  it('does not call Gemini when the frame image is missing', async () => {
    h.readFrameImageBase64.mockResolvedValue(null)
    const a = new MemoryAssistant()
    await a.analyze(frame())
    expect(h.extractMemory).not.toHaveBeenCalled()
  })
})

describe('analyze — extraction pipeline', () => {
  it('persists a memory above the confidence gate, mapping fields from model + frame', async () => {
    h.extractMemory.mockResolvedValue(result())
    const a = new MemoryAssistant()
    await a.analyze(frame({ id: 7, app: 'Slack', windowTitle: 'Acme — general' }))
    expect(h.persistMemory).toHaveBeenCalledTimes(1)
    const [payload, epoch] = h.persistMemory.mock.calls[0]
    expect(payload).toEqual({
      content: 'User works at Acme',
      category: 'system',
      sourceApp: 'Slack',
      contextSummary: 'a workspace',
      windowTitle: 'Acme — general',
      confidence: 0.9,
      screenshotId: 7,
      createdAt: expect.any(Number)
    })
    expect(epoch).toBe(1)
  })

  it('drops a memory below the confidence gate (no persist)', async () => {
    h.settings.memoryMinConfidence = 0.7
    h.extractMemory.mockResolvedValue(
      result({
        memories: [{ content: 'weak', category: 'system', sourceApp: 'X', confidence: 0.6 }]
      })
    )
    const a = new MemoryAssistant()
    await a.analyze(frame())
    expect(h.persistMemory).not.toHaveBeenCalled()
  })

  it('does nothing when the model returns zero memories', async () => {
    h.extractMemory.mockResolvedValue(result({ memories: [] }))
    const a = new MemoryAssistant()
    await a.analyze(frame())
    expect(h.persistMemory).not.toHaveBeenCalled()
  })

  it('maps an interesting category through unchanged', async () => {
    h.extractMemory.mockResolvedValue(
      result({
        memories: [
          {
            content: 'Naval: specific knowledge is learned',
            category: 'interesting',
            sourceApp: 'X',
            confidence: 0.95
          }
        ]
      })
    )
    const a = new MemoryAssistant()
    await a.analyze(frame())
    expect(h.persistMemory.mock.calls[0][0].category).toBe('interesting')
  })

  it('threads the recent-memories dedup list into the user prompt', async () => {
    h.recentMemories.mockReturnValue([{ content: 'User lives in Berlin', category: 'system' }])
    h.extractMemory.mockResolvedValue(result({ memories: [] }))
    const a = new MemoryAssistant()
    await a.analyze(frame({ app: 'Notion' }))
    // extractMemory(session, systemPrompt, userPrompt, imageBase64)
    const userPrompt = h.extractMemory.mock.calls[0][2] as string
    expect(userPrompt).toContain('Analyze this screenshot from Notion.')
    expect(userPrompt).toContain('RECENTLY EXTRACTED MEMORIES')
    expect(userPrompt).toContain('User lives in Berlin')
  })

  it('falls back to the frame app when the model leaves source_app blank', async () => {
    h.extractMemory.mockResolvedValue(
      result({
        memories: [{ content: 'x', category: 'system', sourceApp: '', confidence: 0.9 }]
      })
    )
    const a = new MemoryAssistant()
    await a.analyze(frame({ app: 'Superhuman' }))
    expect(h.persistMemory.mock.calls[0][0].sourceApp).toBe('Superhuman')
  })

  it('does not persist when extraction throws (logged, next interval retries)', async () => {
    h.extractMemory.mockRejectedValue(new Error('boom'))
    const a = new MemoryAssistant()
    await a.analyze(frame())
    expect(h.persistMemory).not.toHaveBeenCalled()
  })
})

describe('analyzeNowForDev — privacy + exclusion gates', () => {
  it('skips (no Gemini) a privacy-denied frame (incognito window)', async () => {
    const a = new MemoryAssistant()
    await a.analyzeNowForDev(
      frame({ app: 'Google Chrome', windowTitle: 'Search — Incognito', processName: 'chrome' })
    )
    expect(h.extractMemory).not.toHaveBeenCalled()
    expect(h.persistMemory).not.toHaveBeenCalled()
  })

  it('skips (no Gemini) a frame whose app is in memoryExcludedApps', async () => {
    h.settings.memoryExcludedApps = ['slack']
    const a = new MemoryAssistant()
    await a.analyzeNowForDev(frame({ app: 'Slack', windowTitle: 'general', processName: 'slack' }))
    expect(h.extractMemory).not.toHaveBeenCalled()
  })

  it('runs the pipeline for an ordinary, allowed frame', async () => {
    h.extractMemory.mockResolvedValue(result())
    const a = new MemoryAssistant()
    await a.analyzeNowForDev(frame({ app: 'VS Code', windowTitle: 'code', processName: 'code' }))
    expect(h.extractMemory).toHaveBeenCalledTimes(1)
    expect(h.persistMemory).toHaveBeenCalledTimes(1)
  })
})
