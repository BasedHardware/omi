import { describe, expect, it } from 'vitest'
import {
  insightFrameAllowed,
  intervalElapsed,
  isUserDeniedApp,
  MAC_EXTRACTION_INTERVAL_MS,
  MIN_CONFIDENCE,
  passesConfidence
} from './gating'
import type { RewindFrame } from '../../../shared/types'

const frame = (over: Partial<RewindFrame> = {}): RewindFrame => ({
  id: 1,
  ts: 1,
  app: 'Terminal',
  windowTitle: 'zsh — build',
  processName: 'WindowsTerminal.exe',
  ocrText: '',
  imagePath: '/f.jpg',
  width: 0,
  height: 0,
  indexed: 1,
  ...over
})

describe('interval cadence (default 600s)', () => {
  it('MAC default anchor is 600s', () => {
    expect(MAC_EXTRACTION_INTERVAL_MS).toBe(600_000)
  })
  it('elapses only once the interval has passed', () => {
    expect(intervalElapsed(599_000, MAC_EXTRACTION_INTERVAL_MS)).toBe(false)
    expect(intervalElapsed(600_000, MAC_EXTRACTION_INTERVAL_MS)).toBe(true)
    expect(intervalElapsed(Number.POSITIVE_INFINITY, MAC_EXTRACTION_INTERVAL_MS)).toBe(true)
  })
})

describe('confidence gate (0.85)', () => {
  it('default is 0.85 and gates strictly below', () => {
    expect(MIN_CONFIDENCE).toBe(0.85)
    expect(passesConfidence(0.85)).toBe(true)
    expect(passesConfidence(0.8499)).toBe(false)
    expect(passesConfidence(0.9)).toBe(true)
  })
})

describe('three-way denylist', () => {
  it('user denylist matches app / title / process substrings, case-insensitive', () => {
    expect(isUserDeniedApp(frame(), ['terminal'])).toBe(true)
    expect(isUserDeniedApp(frame(), ['ZSH'])).toBe(true)
    expect(isUserDeniedApp(frame(), ['windowsterminal.exe'])).toBe(true)
    expect(isUserDeniedApp(frame(), ['slack'])).toBe(false)
  })
  it('empty / blank denylist never matches', () => {
    expect(isUserDeniedApp(frame(), [])).toBe(false)
    expect(isUserDeniedApp(frame(), ['  '])).toBe(false)
  })
  it('insightFrameAllowed folds the user leg into the privacy gate', () => {
    // A normal app with no user denylist entry: allowed.
    expect(insightFrameAllowed(frame({ app: 'Notepad', windowTitle: 'notes' }), [])).toBe(true)
    // Same app, user added it to the denylist: blocked.
    expect(insightFrameAllowed(frame({ app: 'Notepad', windowTitle: 'notes' }), ['Notepad'])).toBe(
      false
    )
  })
  it('insightFrameAllowed blocks a private/denied context regardless of user list', () => {
    // A login page fails the privacy leg (mayAnalyzeFrame) even with an empty user list.
    expect(
      insightFrameAllowed(frame({ app: 'Chrome', windowTitle: 'Sign in - Google Accounts' }), [])
    ).toBe(false)
  })
})
