// @vitest-environment jsdom
// Regression for #10731: "Proactive insights" read as on (and its test
// notification worked) while the pipeline never ran, because InsightAssistant
// additionally requires a deliverable notification — master on AND frequency
// above Off — and frequency ships at 0. The row now says so instead of claiming
// the feature is running.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, screen, configure } from '@testing-library/react'
import { RewindTab } from './RewindTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { AssistantSettingsView, InsightSettings } from '../../../../../shared/types'

vi.setConfig({ testTimeout: 15000 })
configure({ asyncUtilTimeout: 5000 })

const SILENCED_NOTE = /Notifications are off, so insights never run/

const INSIGHT: InsightSettings = {
  enabled: true,
  intervalMin: 15,
  notificationStyle: 'omi',
  denylist: [],
  lastRunAt: null
}

const ASSISTANTS: AssistantSettingsView = {
  notificationsEnabled: true,
  notificationFrequency: 0, // Off — the shipped default
  focusNotificationsEnabled: true,
  memoryEnabled: false,
  glowOverlayEnabled: true,
  screenAnalysisEnabled: true
}

function mockBridge(
  insight: Partial<InsightSettings>,
  assistants: Partial<AssistantSettingsView>
): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).omi = {
    rewindGetSettings: vi.fn(async () => ({
      captureEnabled: true,
      intervalMs: 1000,
      retentionDays: 30,
      excludedApps: [],
      captureQuality: 'balanced'
    })),
    rewindSetSettings: vi.fn(async (s: unknown) => s),
    screenSynthGetState: vi.fn(async () => ({
      enabled: false,
      watermarkTs: 0,
      lastRunAt: null,
      lastCount: 0,
      denylist: []
    })),
    insightGetSettings: vi.fn(async () => ({ ...INSIGHT, ...insight })),
    insightSetSettings: vi.fn(async (p: Partial<InsightSettings>) => ({
      ...INSIGHT,
      ...insight,
      ...p
    })),
    goalsGetAutoGeneration: vi.fn(async () => false),
    assistantsGetSettings: vi.fn(async () => ({ ...ASSISTANTS, ...assistants })),
    onAssistantSettingsChanged: vi.fn(() => () => {})
  }
}

const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <RewindTab />
    </SettingsSearchProvider>
  )
}

afterEach(cleanup)

describe('RewindTab — proactive insights notification gate', () => {
  it('warns that insights never run when the frequency is Off', async () => {
    mockBridge({ enabled: true }, { notificationFrequency: 0 })
    renderTab()
    expect(await screen.findByText(SILENCED_NOTE)).toBeTruthy()
  })

  it('warns when the notifications master toggle is off', async () => {
    mockBridge({ enabled: true }, { notificationsEnabled: false, notificationFrequency: 3 })
    renderTab()
    expect(await screen.findByText(SILENCED_NOTE)).toBeTruthy()
  })

  it('stays quiet once notifications are on and the frequency is above Off', async () => {
    mockBridge({ enabled: true }, { notificationsEnabled: true, notificationFrequency: 3 })
    renderTab()
    await screen.findByText('Proactive insights')
    expect(screen.queryByText(SILENCED_NOTE)).toBeNull()
  })

  it('stays quiet when the user turned insights off themselves', async () => {
    mockBridge({ enabled: false }, { notificationFrequency: 0 })
    renderTab()
    await screen.findByText('Proactive insights')
    expect(screen.queryByText(SILENCED_NOTE)).toBeNull()
  })
})
