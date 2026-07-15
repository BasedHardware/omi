// The assistant's wiring: the master AND-gate, the transition side effects it
// fires (persist / glow / notify), the cold-start-focused silence, and the
// stale-result discard. The pure decision modules are tested separately; here we
// mock every impure collaborator and assert the assistant calls them correctly.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  settings: {
    focusEnabled: true,
    focusNotificationsEnabled: true,
    focusCooldownMinutes: 10,
    focusExcludedApps: [] as string[]
  },
  showGlow: vi.fn(),
  notifyProactive: vi.fn(),
  persistFocusSession: vi.fn(() => 1),
  readFrameImageBase64: vi.fn(async (): Promise<string | null> => 'BASE64'),
  getBackendSession: vi.fn(
    (): { apiBase: string; desktopApiBase: string; token: string } | null => ({
      apiBase: 'a',
      desktopApiBase: 'd',
      token: 't'
    })
  ),
  loadFocusContext: vi.fn(async () => ({
    profileText: null,
    goals: [],
    tasks: [],
    memories: [],
    now: new Date('2026-07-14T15:00:00')
  })),
  getFocusSystemPrompt: vi.fn(() => 'SYSTEM'),
  analyzeScreenshot: vi.fn()
}))

vi.mock('../../appSettings', () => ({ getAppSettings: () => h.settings }))
vi.mock('../../glow/glowWindow', () => ({ showGlow: h.showGlow }))
vi.mock('../core/notify', () => ({ notifyProactive: h.notifyProactive }))
vi.mock('./persist', () => ({ persistFocusSession: h.persistFocusSession }))
vi.mock('../core/frameImage', () => ({ readFrameImageBase64: h.readFrameImageBase64 }))
vi.mock('../core/session', () => ({
  getBackendSession: h.getBackendSession,
  getSessionEpoch: () => 1
}))
vi.mock('./context', () => ({ loadFocusContext: h.loadFocusContext }))
vi.mock('./promptStore', () => ({ getFocusSystemPrompt: h.getFocusSystemPrompt }))
vi.mock('./gemini', () => ({ analyzeScreenshot: h.analyzeScreenshot }))

import { FocusAssistant } from './focusAssistant'
import type { RewindFrame } from '../../../shared/types'
import type { ScreenAnalysis } from './models'

function frame(over: Partial<RewindFrame> = {}): RewindFrame {
  return {
    id: 1,
    ts: 1000,
    app: 'Chrome',
    windowTitle: 'Docs',
    processName: 'chrome',
    ocrText: '',
    imagePath: 'C:/x.jpg',
    width: 100,
    height: 100,
    indexed: 0,
    ...over
  }
}

const verdict = (over: Partial<ScreenAnalysis> = {}): ScreenAnalysis => ({
  status: 'distracted',
  appOrSite: 'YouTube',
  description: 'a video',
  message: 'refocus',
  ...over
})

beforeEach(() => {
  h.settings.focusEnabled = true
  h.settings.focusNotificationsEnabled = true
  h.settings.focusExcludedApps = []
  vi.clearAllMocks()
  h.persistFocusSession.mockReturnValue(1)
  h.readFrameImageBase64.mockResolvedValue('BASE64')
  h.getBackendSession.mockReturnValue({ apiBase: 'a', desktopApiBase: 'd', token: 't' })
})

afterEach(() => vi.restoreAllMocks())

describe('isEnabled — the master AND-gate', () => {
  it('is true only when BOTH focusEnabled and focusNotificationsEnabled are on', () => {
    const a = new FocusAssistant()
    expect(a.isEnabled()).toBe(true)

    h.settings.focusNotificationsEnabled = false
    expect(a.isEnabled()).toBe(false) // Mac: no notification setting → no analysis

    h.settings.focusNotificationsEnabled = true
    h.settings.focusEnabled = false
    expect(a.isEnabled()).toBe(false)
  })

  it('is false after stop()', () => {
    const a = new FocusAssistant()
    a.stop()
    expect(a.isEnabled()).toBe(false)
  })
})

describe('analyze — local gates', () => {
  it('hard-skips a lock-screen frame without calling Gemini', async () => {
    const a = new FocusAssistant()
    await a.analyze(frame({ app: 'LockApp', processName: 'LockApp.exe' }))
    expect(h.analyzeScreenshot).not.toHaveBeenCalled()
  })

  it('skips an excluded app', async () => {
    h.settings.focusExcludedApps = ['slack']
    const a = new FocusAssistant()
    await a.analyze(frame({ app: 'Slack', processName: 'slack' }))
    expect(h.analyzeScreenshot).not.toHaveBeenCalled()
  })

  it('does not call Gemini with no backend session', async () => {
    h.getBackendSession.mockReturnValue(null)
    const a = new FocusAssistant()
    await a.analyze(frame())
    expect(h.analyzeScreenshot).not.toHaveBeenCalled()
  })

  it('does not call Gemini when the frame image is missing', async () => {
    h.readFrameImageBase64.mockResolvedValue(null)
    const a = new FocusAssistant()
    await a.analyze(frame())
    expect(h.analyzeScreenshot).not.toHaveBeenCalled()
  })
})

describe('analyze — transitions', () => {
  it('cold-start focused: persists but does NOT glow or notify', async () => {
    h.analyzeScreenshot.mockResolvedValue(verdict({ status: 'focused', message: 'nice' }))
    const a = new FocusAssistant()
    await a.analyze(frame())
    expect(h.persistFocusSession).toHaveBeenCalledTimes(1)
    expect(h.showGlow).not.toHaveBeenCalled()
    expect(h.notifyProactive).not.toHaveBeenCalled()
  })

  it('→ distracted: persists, red glow, throttled notification', async () => {
    const a = new FocusAssistant()
    // First make it focused (cold start, silent), then distracted (transition).
    h.analyzeScreenshot.mockResolvedValueOnce(verdict({ status: 'focused', message: 'ok' }))
    await a.analyze(frame({ app: 'VS Code', windowTitle: 'code' }))

    h.analyzeScreenshot.mockResolvedValueOnce(verdict({ status: 'distracted', message: 'hey' }))
    await a.analyze(frame({ app: 'Chrome', windowTitle: 'YouTube' }))

    expect(h.showGlow).toHaveBeenCalledWith('distracted')
    expect(h.notifyProactive).toHaveBeenCalledTimes(1)
    const [, payload] = h.notifyProactive.mock.calls[0]
    expect(payload.advice).toBe('YouTube - hey')
  })

  it('does not re-glow or re-notify on a second distracted verdict (dedup)', async () => {
    const a = new FocusAssistant()
    h.analyzeScreenshot.mockResolvedValueOnce(verdict({ status: 'focused' }))
    await a.analyze(frame({ app: 'VS Code', windowTitle: 'code' }))
    h.analyzeScreenshot.mockResolvedValueOnce(verdict({ status: 'distracted' }))
    await a.analyze(frame({ app: 'Chrome', windowTitle: 'YouTube' }))
    h.showGlow.mockClear()
    h.notifyProactive.mockClear()
    // Same distracting context again → the skip gate would normally stop it, so
    // force a context change to a different distraction to re-run analyze; still
    // distracted, so still no NEW transition.
    h.analyzeScreenshot.mockResolvedValueOnce(
      verdict({ status: 'distracted', appOrSite: 'Reddit' })
    )
    await a.analyze(frame({ app: 'Chrome', windowTitle: 'Reddit' }))
    expect(h.showGlow).not.toHaveBeenCalled()
    expect(h.notifyProactive).not.toHaveBeenCalled()
  })

  it('→ focused from distracted: green glow, message-only notification', async () => {
    const a = new FocusAssistant()
    h.analyzeScreenshot.mockResolvedValueOnce(verdict({ status: 'focused' }))
    await a.analyze(frame({ app: 'VS Code', windowTitle: 'code' }))
    h.analyzeScreenshot.mockResolvedValueOnce(verdict({ status: 'distracted' }))
    await a.analyze(frame({ app: 'Chrome', windowTitle: 'YouTube' }))
    h.showGlow.mockClear()
    h.notifyProactive.mockClear()

    h.analyzeScreenshot.mockResolvedValueOnce(
      verdict({ status: 'focused', appOrSite: 'VS Code', message: 'welcome back' })
    )
    await a.analyze(frame({ app: 'VS Code', windowTitle: 'code again' }))
    expect(h.showGlow).toHaveBeenCalledWith('focused')
    const [, payload] = h.notifyProactive.mock.calls[0]
    expect(payload.advice).toBe('welcome back') // no app prefix
  })
})

describe('analyze — error backoff', () => {
  it('a thrown Gemini error sets a backoff that skips the next frame', async () => {
    const a = new FocusAssistant()
    h.analyzeScreenshot.mockRejectedValueOnce(new Error('boom'))
    await a.analyze(frame())
    expect(h.persistFocusSession).not.toHaveBeenCalled()
    // The next frame (still cold start) is skipped by the backoff, so Gemini is
    // not called again immediately.
    h.analyzeScreenshot.mockClear()
    await a.analyze(frame({ id: 2, ts: 2000 }))
    expect(h.analyzeScreenshot).not.toHaveBeenCalled()
  })
})

describe('analyzeNowForDev — privacy + exclusion gates', () => {
  it('skips (no Gemini) a privacy-denied frame (incognito window)', async () => {
    const a = new FocusAssistant()
    await a.analyzeNowForDev(
      frame({ app: 'Google Chrome', windowTitle: 'Search — Incognito', processName: 'chrome' })
    )
    expect(h.analyzeScreenshot).not.toHaveBeenCalled()
    expect(h.persistFocusSession).not.toHaveBeenCalled()
  })

  it('skips (no Gemini) a frame whose app is in focusExcludedApps', async () => {
    h.settings.focusExcludedApps = ['slack']
    const a = new FocusAssistant()
    await a.analyzeNowForDev(frame({ app: 'Slack', windowTitle: 'general', processName: 'slack' }))
    expect(h.analyzeScreenshot).not.toHaveBeenCalled()
    expect(h.persistFocusSession).not.toHaveBeenCalled()
  })

  it('runs the pipeline for an ordinary, allowed frame', async () => {
    h.analyzeScreenshot.mockResolvedValue(verdict({ status: 'focused' }))
    const a = new FocusAssistant()
    await a.analyzeNowForDev(frame({ app: 'VS Code', windowTitle: 'code', processName: 'code' }))
    expect(h.analyzeScreenshot).toHaveBeenCalledTimes(1)
  })
})

describe('clearPendingWork — context-switch discard', () => {
  it('discards a verdict whose run predates a context switch (no glow/notify/persist)', async () => {
    const a = new FocusAssistant()
    let resolveA!: (v: ScreenAnalysis) => void
    h.analyzeScreenshot.mockImplementationOnce(
      () => new Promise<ScreenAnalysis>((res) => (resolveA = res))
    )
    const runA = a.analyze(frame({ app: 'VS Code', windowTitle: 'code' }))
    // Let run A progress until it is parked inside the (pending) Gemini call.
    await new Promise((r) => setTimeout(r, 0))
    expect(h.analyzeScreenshot).toHaveBeenCalledTimes(1)

    // The context switches under the in-flight run: minValidSeq is raised above
    // run A's seq, so A's verdict must be discarded when it lands.
    a.clearPendingWork()
    resolveA(verdict({ status: 'distracted' }))
    await runA

    expect(h.persistFocusSession).not.toHaveBeenCalled()
    expect(h.showGlow).not.toHaveBeenCalled()
    expect(h.notifyProactive).not.toHaveBeenCalled()
  })
})

describe('analyzeNowForDev — stale-result discard', () => {
  it('discards an older run whose result lands after a newer run committed', async () => {
    const a = new FocusAssistant()
    // Two overlapping runs: run A resolves LAST but started FIRST.
    let resolveA!: (v: ScreenAnalysis) => void
    h.analyzeScreenshot
      .mockImplementationOnce(() => new Promise<ScreenAnalysis>((res) => (resolveA = res)))
      .mockResolvedValueOnce(verdict({ status: 'distracted', appOrSite: 'Reddit' }))

    const runA = a.analyzeNowForDev(frame({ app: 'Chrome', windowTitle: 'YouTube' }))
    // run B starts and finishes while A is still pending.
    await a.analyzeNowForDev(frame({ app: 'Chrome', windowTitle: 'Reddit' }))
    const persistsAfterB = h.persistFocusSession.mock.calls.length
    expect(persistsAfterB).toBe(1) // B committed

    // Now A resolves — it is stale (older seq than B), so it must be discarded.
    resolveA(verdict({ status: 'distracted', appOrSite: 'YouTube' }))
    await runA
    expect(h.persistFocusSession.mock.calls.length).toBe(persistsAfterB) // no new persist
  })
})
