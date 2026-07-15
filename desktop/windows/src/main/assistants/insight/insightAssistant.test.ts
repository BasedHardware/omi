// The assistant wiring: the enablement gate, the user-denylist skip, the
// confidence filter, and delivery (persist + notify, never a glow). The pure
// pieces (gating, prompt) run real; the boundaries (gemini pipeline, persist,
// notify, context fetches, settings, session) are mocked.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  appSettings: { notificationsEnabled: true },
  insightSettings: { enabled: true, intervalMin: 10, denylist: [] as string[] },
  runTwoPhasePipeline: vi.fn(),
  persistInsight: vi.fn((): number | null => 1),
  notifyProactive: vi.fn(() => true),
  notificationsActive: vi.fn(() => true),
  runReadonlySelect: vi.fn(() => ({ columns: [] as string[], rows: [] as unknown[][] })),
  getBackendSession: vi.fn(
    (): { apiBase: string; desktopApiBase: string; token: string } | null => ({
      apiBase: 'a',
      desktopApiBase: 'd',
      token: 't'
    })
  ),
  getSessionEpoch: vi.fn(() => 7),
  getUserLanguage: vi.fn(async () => null),
  loadInsightContext: vi.fn(() => ({
    currentApp: 'Terminal',
    currentWindowTitle: null,
    now: new Date(),
    profileText: null,
    activity: [],
    activitySpanMinutes: 10,
    previousInsights: []
  }))
}))

vi.mock('../../appSettings', () => ({ getAppSettings: () => h.appSettings }))
vi.mock('../../insight/state', () => ({ getInsightSettings: () => h.insightSettings }))
vi.mock('../core/notify', () => ({
  notifyProactive: h.notifyProactive,
  notificationsActive: h.notificationsActive
}))
vi.mock('../core/session', () => ({
  getBackendSession: h.getBackendSession,
  getSessionEpoch: h.getSessionEpoch
}))
vi.mock('../core/frameImage', () => ({ readFrameImageBase64: async () => null }))
vi.mock('../../ipc/db', () => ({
  runReadonlySelect: h.runReadonlySelect,
  rewindFramesByIds: vi.fn(() => [])
}))
vi.mock('./gemini', () => ({ runTwoPhasePipeline: h.runTwoPhasePipeline }))
vi.mock('./persist', async () => {
  const actual = await vi.importActual<typeof import('./persist')>('./persist')
  return { persistInsight: h.persistInsight, toPayload: actual.toPayload }
})
vi.mock('./promptStore', () => ({ getInsightAnalysisPrompt: () => 'PROMPT' }))
vi.mock('./context', () => ({
  getUserLanguage: h.getUserLanguage,
  loadInsightContext: h.loadInsightContext,
  MAX_LOOKBACK_MS: 3_600_000
}))

import { InsightAssistant } from './insightAssistant'
import type { RewindFrame } from '../../../shared/types'
import type { ExtractedInsight } from './models'

const frame = (over: Partial<RewindFrame> = {}): RewindFrame => ({
  id: 1,
  ts: 1,
  app: 'Terminal',
  windowTitle: 'zsh',
  processName: 'WindowsTerminal.exe',
  ocrText: '',
  imagePath: '/f.jpg',
  width: 0,
  height: 0,
  indexed: 1,
  ...over
})

const insight = (conf: number): ExtractedInsight => ({
  advice: 'Mask the token',
  headline: 'Token visible',
  reasoning: null,
  category: 'productivity',
  sourceApp: 'Terminal',
  confidence: conf,
  contextSummary: 'c',
  currentActivity: 'a'
})

beforeEach(() => {
  vi.clearAllMocks()
  h.appSettings = { notificationsEnabled: true }
  h.insightSettings = { enabled: true, intervalMin: 10, denylist: [] }
  h.persistInsight.mockReturnValue(1)
  h.notificationsActive.mockReturnValue(true)
  h.runReadonlySelect.mockReturnValue({ columns: [], rows: [] })
  h.getSessionEpoch.mockReturnValue(7)
  h.getBackendSession.mockReturnValue({ apiBase: 'a', desktopApiBase: 'd', token: 't' })
})

afterEach(() => vi.restoreAllMocks())

describe('isEnabled', () => {
  it('requires the feature toggle AND a deliverable notification (notificationsActive)', () => {
    const a = new InsightAssistant()
    expect(a.isEnabled()).toBe(true)
    // Feature toggle off → disabled.
    h.insightSettings.enabled = false
    expect(a.isEnabled()).toBe(false)
    // Feature on but notifications effectively silenced (off / freq 0 / snoozed) →
    // disabled: a glow-less Insight run whose toast can't appear is wasted spend.
    h.insightSettings.enabled = true
    h.notificationsActive.mockReturnValue(false)
    expect(a.isEnabled()).toBe(false)
    // Both on → enabled.
    h.notificationsActive.mockReturnValue(true)
    expect(a.isEnabled()).toBe(true)
  })
  it('is false after stop()', () => {
    const a = new InsightAssistant()
    a.stop()
    expect(a.isEnabled()).toBe(false)
  })
})

describe('analyze', () => {
  it('delivers an above-threshold insight: persist + notify, never returns a result', async () => {
    h.runTwoPhasePipeline.mockResolvedValue({ insight: insight(0.9), sqlCount: 2 })
    const a = new InsightAssistant()
    const out = await a.analyze(frame())
    expect(out).toBeNull()
    expect(h.persistInsight).toHaveBeenCalledWith(expect.objectContaining({ confidence: 0.9 }), 7)
    expect(h.notifyProactive).toHaveBeenCalledWith(
      'insight',
      expect.objectContaining({ headline: 'Token visible', advice: 'Mask the token' })
    )
  })

  it('drops a below-threshold insight (no persist, no notify)', async () => {
    h.runTwoPhasePipeline.mockResolvedValue({ insight: insight(0.5), sqlCount: 0 })
    await new InsightAssistant().analyze(frame())
    expect(h.persistInsight).not.toHaveBeenCalled()
    expect(h.notifyProactive).not.toHaveBeenCalled()
  })

  it('does not notify when persist drops the write (session changed)', async () => {
    h.runTwoPhasePipeline.mockResolvedValue({ insight: insight(0.9), sqlCount: 0 })
    h.persistInsight.mockReturnValue(null)
    await new InsightAssistant().analyze(frame())
    expect(h.notifyProactive).not.toHaveBeenCalled()
  })

  it('skips the pipeline entirely for a user-denied app', async () => {
    h.insightSettings.denylist = ['Terminal']
    await new InsightAssistant().analyze(frame())
    expect(h.runTwoPhasePipeline).not.toHaveBeenCalled()
  })

  it('no-ops (no pipeline) when there is no backend session yet', async () => {
    h.getBackendSession.mockReturnValue(null)
    await new InsightAssistant().analyze(frame())
    expect(h.runTwoPhasePipeline).not.toHaveBeenCalled()
  })

  it('threads the user denylist into the Phase-1 activity context', async () => {
    // FIX 4(a): the denylist must reach loadInsightContext even when Insight
    // triggered on a DIFFERENT, allowed app (here Terminal).
    h.insightSettings.denylist = ['Signal']
    h.runTwoPhasePipeline.mockResolvedValue({ insight: null, sqlCount: 0 })
    await new InsightAssistant().analyze(frame())
    expect(h.loadInsightContext).toHaveBeenCalledWith(
      expect.objectContaining({ denylist: ['Signal'] })
    )
  })

  it('binds the denylist into the execute_sql closure (denied rows shadow-filtered)', async () => {
    // FIX 4(b): the execSql the pipeline receives is bound to the denylist, so a
    // `WHERE app='Signal'` query is rewritten to a filtered CTE before it runs.
    h.insightSettings.denylist = ['Signal']
    let opts: { execSql: (q: string) => string } | undefined
    h.runTwoPhasePipeline.mockImplementation(async (o: unknown) => {
      opts = o as { execSql: (q: string) => string }
      return { insight: null, sqlCount: 0 }
    })
    await new InsightAssistant().analyze(frame())
    opts!.execSql("SELECT ocr_text FROM rewind_frames WHERE app='Signal'")
    expect(h.runReadonlySelect).toHaveBeenCalledWith(
      expect.stringContaining('WITH rewind_frames AS')
    )
  })
})

describe('shouldAnalyze — fixed interval', () => {
  it('respects the intervalMin picker (10 min here)', () => {
    const a = new InsightAssistant()
    expect(a.shouldAnalyze(1, 9 * 60_000)).toBe(false)
    expect(a.shouldAnalyze(1, 10 * 60_000)).toBe(true)
  })
})
