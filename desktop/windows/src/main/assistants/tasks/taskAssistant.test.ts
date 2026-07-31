// The Task assistant's gates + triggers, hermetic. The pure app/window gate and
// the cadence intervals are asserted directly; the pipeline (loop + create) is
// faked so analyze/onContextSwitch are tested for the confidence gate, the
// epoch/seq stale-guard, and the re-entrancy lock — with no DB, network, or
// Electron.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RewindFrame } from '../../../shared/types'
import type { ExtractedTask } from './models'

const h = vi.hoisted(() => ({
  epoch: 5,
  settings: {
    taskEnabled: true,
    taskExcludedApps: [] as string[],
    taskFallbackIntervalMin: 10,
    taskMinConfidence: 0.75,
    screenAnalysisEnabled: true
  } as Record<string, unknown>,
  getSessionEpoch: vi.fn(() => h.epoch),
  getBackendSession: vi.fn(() => ({ apiBase: 'https://api', desktopApiBase: 'https://d', token: 't' })),
  readFrameImageBase64: vi.fn(async () => 'imgdata'),
  mayAnalyzeFrame: vi.fn(() => true),
  runExtractionLoop: vi.fn(async (..._a: unknown[]) => [] as ExtractedTask[]),
  createStagedTaskFromExtraction: vi.fn(async (..._a: unknown[]) => {})
}))

vi.mock('../../appSettings', () => ({ getAppSettings: () => h.settings }))
vi.mock('../core/session', () => ({
  getSessionEpoch: h.getSessionEpoch,
  getBackendSession: h.getBackendSession
}))
vi.mock('../core/frameImage', () => ({ readFrameImageBase64: h.readFrameImageBase64 }))
vi.mock('../core/privacy', () => ({ mayAnalyzeFrame: h.mayAnalyzeFrame }))
vi.mock('./loop', () => ({ runExtractionLoop: h.runExtractionLoop }))
vi.mock('./create', () => ({ createStagedTaskFromExtraction: h.createStagedTaskFromExtraction }))

import { TaskAssistant, shouldExtractForApp } from './taskAssistant'

// --- Fixtures ---------------------------------------------------------------

function makeTask(overrides: Partial<ExtractedTask> = {}): ExtractedTask {
  return {
    title: 'Send Priya the onboarding deck by Friday',
    description: 'Priya asked',
    priority: 'high',
    sourceApp: 'Slack',
    inferredDeadline: null,
    confidence: 0.9,
    tags: ['work'],
    sourceCategory: 'direct_request',
    sourceSubcategory: 'message',
    captureKind: 'clear_commitment',
    owner: 'user',
    concreteDeliverable: true,
    publicBroadcast: false,
    directMention: true,
    alreadyDone: false,
    duplicateOf: null,
    refinesTask: null,
    ownershipConfidence: 0.8,
    contextSummary: 'A Slack DM',
    currentActivity: 'Reading Priya',
    ...overrides
  }
}

function makeFrame(overrides: Partial<RewindFrame> = {}): RewindFrame {
  return {
    id: 7,
    ts: 1000,
    app: 'Slack',
    windowTitle: 'Acme — general',
    processName: 'slack',
    ocrText: '',
    imagePath: '/tmp/f.jpg',
    width: 0,
    height: 0,
    indexed: 1,
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  h.epoch = 5
  h.settings = {
    taskEnabled: true,
    taskExcludedApps: [],
    taskFallbackIntervalMin: 10,
    taskMinConfidence: 0.75,
    screenAnalysisEnabled: true
  }
  h.getSessionEpoch.mockImplementation(() => h.epoch)
  h.getBackendSession.mockReturnValue({ apiBase: 'https://api', desktopApiBase: 'https://d', token: 't' })
  h.readFrameImageBase64.mockResolvedValue('imgdata')
  h.mayAnalyzeFrame.mockReturnValue(true)
  h.runExtractionLoop.mockResolvedValue([])
})

afterEach(() => vi.restoreAllMocks())

// --- isEnabled truth table ---------------------------------------------------

describe('isEnabled', () => {
  it('is true only when taskEnabled and not stopped', () => {
    const a = new TaskAssistant()
    h.settings.taskEnabled = true
    expect(a.isEnabled()).toBe(true)

    h.settings.taskEnabled = false
    expect(a.isEnabled()).toBe(false)

    h.settings.taskEnabled = true
    a.stop()
    expect(a.isEnabled()).toBe(false) // stopped short-circuits even with the flag on
  })
})

// --- The pure app/window gate ------------------------------------------------

describe('shouldExtractForApp', () => {
  it('allows a whitelisted non-browser app (Slack)', () => {
    expect(shouldExtractForApp('Slack', 'Acme — general', [])).toBe(true)
  })

  it('rejects a non-whitelisted app (Steam)', () => {
    expect(shouldExtractForApp('Steam', 'Store', [])).toBe(false)
  })

  it('rejects a whitelisted app on the user excluded list', () => {
    expect(shouldExtractForApp('Slack', 'Acme', ['slack'])).toBe(false)
  })

  it('allows a browser only when the window title clears a keyword', () => {
    expect(shouldExtractForApp('Chrome', 'Gmail - Inbox (3)', [])).toBe(true)
    expect(shouldExtractForApp('Chrome', 'reddit - funny', [])).toBe(false)
  })
})

// --- shouldAnalyze cadence ---------------------------------------------------

describe('shouldAnalyze', () => {
  it('uses the 15s messaging interval for a messaging app', () => {
    const a = new TaskAssistant()
    a.onContextSwitch(null, 'Slack', null) // sets the current app (no frame → no run)
    expect(a.shouldAnalyze(1, 14_000)).toBe(false)
    expect(a.shouldAnalyze(1, 15_000)).toBe(true)
  })

  it('uses the fallback minutes interval for a non-messaging app', () => {
    const a = new TaskAssistant()
    a.onContextSwitch(null, 'Notion', null)
    expect(a.shouldAnalyze(1, 599_000)).toBe(false) // 10 min default = 600s
    expect(a.shouldAnalyze(1, 600_000)).toBe(true)
  })
})

// --- analyze: confidence gate + save ----------------------------------------

describe('analyze — confidence gate', () => {
  it('stages a task at/above the threshold', async () => {
    h.runExtractionLoop.mockResolvedValue([makeTask({ confidence: 0.9 })])
    await new TaskAssistant().analyze(makeFrame())
    expect(h.createStagedTaskFromExtraction).toHaveBeenCalledTimes(1)
    const [t, frame, epoch, , minConf] = h.createStagedTaskFromExtraction.mock.calls[0]
    expect((t as ExtractedTask).confidence).toBe(0.9)
    expect((frame as RewindFrame).app).toBe('Slack')
    expect(epoch).toBe(5)
    expect(minConf).toBe(0.75) // the user threshold is threaded to create too
  })

  it('drops a sub-threshold task with no save', async () => {
    h.runExtractionLoop.mockResolvedValue([makeTask({ confidence: 0.74 })])
    await new TaskAssistant().analyze(makeFrame())
    expect(h.createStagedTaskFromExtraction).not.toHaveBeenCalled()
  })

  it('does not run the pipeline for a non-whitelisted app', async () => {
    await new TaskAssistant().analyze(makeFrame({ app: 'Steam', windowTitle: 'Store' }))
    expect(h.runExtractionLoop).not.toHaveBeenCalled()
  })

  it('skips the batch when the session epoch advances during the loop', async () => {
    h.runExtractionLoop.mockImplementation(async () => {
      h.epoch = 6 // sign-out / user switch landed mid-extraction
      return [makeTask({ confidence: 0.9 })]
    })
    await new TaskAssistant().analyze(makeFrame())
    expect(h.createStagedTaskFromExtraction).not.toHaveBeenCalled()
  })
})

// --- onContextSwitch: departing frame + gating ------------------------------

describe('onContextSwitch', () => {
  it('extracts from the DEPARTING frame, not the new context', async () => {
    h.runExtractionLoop.mockResolvedValue([makeTask()])
    const departing = makeFrame({ app: 'Slack', windowTitle: 'Acme — general' })
    await new TaskAssistant().onContextSwitch(departing, 'Chrome', null)
    expect(h.runExtractionLoop).toHaveBeenCalledTimes(1)
    expect(h.runExtractionLoop.mock.calls[0][0]).toMatchObject({ app: 'Slack' })
    expect(h.createStagedTaskFromExtraction).toHaveBeenCalledTimes(1)
  })

  it('does nothing when disabled (the coordinator does not gate this seam)', async () => {
    h.settings.taskEnabled = false
    await new TaskAssistant().onContextSwitch(makeFrame(), 'Chrome', null)
    expect(h.runExtractionLoop).not.toHaveBeenCalled()
  })

  it('no-ops with no departing frame and no prior frame', async () => {
    await new TaskAssistant().onContextSwitch(null, 'Slack', null)
    expect(h.runExtractionLoop).not.toHaveBeenCalled()
  })
})

// --- Re-entrancy lock --------------------------------------------------------

describe('re-entrancy', () => {
  it('does not let a context-switch run overlap an in-flight analyze run', async () => {
    let release!: () => void
    h.runExtractionLoop.mockImplementation(
      () => new Promise((r) => (release = () => r([makeTask()])))
    )
    const a = new TaskAssistant()
    const p = a.analyze(makeFrame()) // starts the pipeline, holds the lock
    await new Promise((r) => setTimeout(r, 0)) // flush to the parked runExtractionLoop
    // A context switch arrives mid-analyze — must be dropped, not run in parallel.
    await a.onContextSwitch(makeFrame({ app: 'Telegram', windowTitle: 'Chat' }), 'Chrome', null)
    expect(h.runExtractionLoop).toHaveBeenCalledTimes(1)
    release()
    await p
    expect(h.createStagedTaskFromExtraction).toHaveBeenCalledTimes(1)
  })
})

// --- Per-window dedupe -------------------------------------------------------

describe('per-window dedupe', () => {
  it('skips re-analyzing the same window within the TTL', async () => {
    h.runExtractionLoop.mockResolvedValue([])
    const a = new TaskAssistant()
    // Notes is whitelisted + non-messaging (60s dedupe TTL) + not a browser.
    const frame = makeFrame({ app: 'Notes', windowTitle: 'Roadmap' })
    await a.analyze(frame)
    await a.analyze(frame) // same window, immediately — deduped
    expect(h.runExtractionLoop).toHaveBeenCalledTimes(1)
  })
})
