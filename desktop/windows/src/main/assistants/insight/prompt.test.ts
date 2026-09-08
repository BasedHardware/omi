// SCA-358: the shipped Insight prompt taught the model that 2026 dates are
// mistakes ("You've scheduled this for 2026 — double-check the year") while the
// Phase-1 user prompt carried only "3:07 PM, Monday" — no year, no timezone.
// These tests pin the fix: the teaching example is retired, the version bump
// wipes saved custom prompts, and every Phase-1 request states the full local
// date and timezone. Mirrors Mac's ProactiveDateGroundingTests.
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'

let userDataDir: string | null = null
vi.mock('electron', () => ({
  app: {
    getPath: () => {
      if (!userDataDir) userDataDir = mkdtempSync(join(tmpdir(), 'insight-prompt-'))
      return userDataDir
    }
  }
}))

import {
  CURRENT_PROMPT_VERSION,
  DEFAULT_ANALYSIS_PROMPT,
  buildPhase1Prompt,
  formatDateTime,
  type InsightContextData
} from './prompt'
import {
  _resetInsightPromptCache,
  getInsightAnalysisPrompt,
  migrateInsightPromptIfNeeded
} from './promptStore'

afterEach(() => {
  _resetInsightPromptCache()
  if (userDataDir) {
    rmSync(userDataDir, { recursive: true, force: true })
    userDataDir = null
  }
})

describe('insight default prompt (SCA-358)', () => {
  it('retires the wrong-year teaching example and adds date grounding', () => {
    expect(DEFAULT_ANALYSIS_PROMPT).not.toContain('double-check the year')
    // The replacement keeps the calendar-mistake class without year suspicion.
    expect(DEFAULT_ANALYSIS_PROMPT).toContain('double-check the date')
    expect(DEFAULT_ANALYSIS_PROMPT).toContain('DATE GROUNDING')
    expect(DEFAULT_ANALYSIS_PROMPT).toContain('never say the clock, calendar, or year')
  })

  it('carries no live timestamp in the cached system prompt', () => {
    expect(DEFAULT_ANALYSIS_PROMPT).not.toMatch(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)
  })
  it('bumps the prompt version so saved custom prompts are wiped', () => {
    expect(CURRENT_PROMPT_VERSION).toBe(3)
    // First read initializes the mocked userData directory.
    expect(getInsightAnalysisPrompt()).toBe(DEFAULT_ANALYSIS_PROMPT)
    if (!userDataDir) throw new Error('userData dir not initialized')
    writeFileSync(
      join(userDataDir, 'insight-prompt.json'),
      JSON.stringify({ version: 2, customPrompt: 'my stale custom prompt' })
    )
    _resetInsightPromptCache()

    migrateInsightPromptIfNeeded()

    expect(getInsightAnalysisPrompt()).toBe(DEFAULT_ANALYSIS_PROMPT)
  })
})

describe('insight phase-1 date grounding', () => {
  it('formats the full local datetime with an explicit timezone', () => {
    expect(formatDateTime(new Date('2026-08-25T19:45:00Z'), 'America/New_York')).toBe(
      'Tuesday, August 25, 2026 at 3:45 PM (America/New_York)'
    )
  })

  it('states the full date and timezone in the user-turn head', () => {
    const data: InsightContextData = {
      currentApp: 'Calendar',
      currentWindowTitle: 'October',
      now: new Date('2026-08-25T19:45:00Z'),
      profileText: null,
      activity: [],
      activitySpanMinutes: 0,
      previousInsights: []
    }

    const prompt = buildPhase1Prompt(data)

    // The runner's local zone decides the wall clock. Pin the exact host-local
    // rendering so every IANA timezone exercises the same contract.
    const expectedDateTime = formatDateTime(data.now)
    expect(prompt).toContain(`Date/Time: ${expectedDateTime}.`)
    expect(prompt).toContain('CURRENT APP: Calendar.')
    expect(prompt).toContain('Window: "October".')
  })
})
