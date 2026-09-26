// The built-in Rewind exclusions are a privacy list: password managers whose
// windows must never be stored, and screen-recording tools that would otherwise
// capture a recording of a recording. Nothing tested either list. It is reached
// only indirectly, through `captureDecision`, and only three of the twelve
// window-title markers were exercised there.
//
// A privacy list is exactly the kind of thing that decays without a contract:
// entries get added over time, and the failure mode of a wrong one is silent in
// both directions. An entry that stops matching means a password manager is
// recorded, which is a breach. An entry that matches too much means an ordinary
// app is never recorded, which the user experiences as Rewind quietly having
// holes in it. Both are invisible without a test.
//
// These iterate the REAL exported arrays rather than a copy, so an entry added
// later is covered the day it lands.
import { describe, expect, it } from 'vitest'
import { BUILT_IN_EXCLUDED_APPS, SENSITIVE_WINDOW_MARKERS } from './rewindExclusions'
import { shouldCaptureFrame, type CaptureState } from '../main/rewind/captureDecision'

/** A frame that would otherwise be captured, so any refusal is the rule firing. */
const capturable: CaptureState = {
  locked: false,
  idleSeconds: 0,
  idleThresholdSeconds: 60,
  busy: false,
  appName: 'SomeOrdinaryApp',
  processName: 'someordinaryapp.exe',
  windowTitle: 'Untitled document',
  excludedApps: [...BUILT_IN_EXCLUDED_APPS],
  hash: '1111000011110000',
  lastHash: '0000111100001111',
  nowMs: 1_000_000,
  lastCapturedAtMs: 995_000
}

describe('the frame this file uses as its control', () => {
  it('is captured, so every refusal below is a rule firing', () => {
    expect(shouldCaptureFrame(capturable)).toEqual({ capture: true })
  })
})

describe('built-in app exclusions', () => {
  it('has not silently shrunk', () => {
    // A count, so removing an entry is not invisible. The per-entry cases below
    // all iterate the list, so they get shorter with it and stay green.
    expect(BUILT_IN_EXCLUDED_APPS).toHaveLength(21)
  })

  it.each(BUILT_IN_EXCLUDED_APPS)('never captures %s', (app) => {
    expect(shouldCaptureFrame({ ...capturable, appName: app })).toEqual({
      capture: false,
      reason: 'excluded'
    })
  })

  const SINGLE_TOKEN = BUILT_IN_EXCLUDED_APPS.filter((a) => !a.includes(' '))
  const MULTI_TOKEN = BUILT_IN_EXCLUDED_APPS.filter((a) => a.includes(' '))

  it.each(SINGLE_TOKEN)('never captures %s by process name alone', (app) => {
    // The app name and the process name are matched together as one string, so
    // a single-token entry catches the app even when Windows reports only the
    // executable.
    expect(
      shouldCaptureFrame({
        ...capturable,
        appName: 'Unknown',
        processName: `${app.toLowerCase()}.exe`
      })
    ).toEqual({ capture: false, reason: 'excluded' })
  })

  it.each(MULTI_TOKEN)('%s is matched by app name only, never by process name', (app) => {
    // Found by writing the case above and watching it fail. Four entries
    // contain a space, and a Windows process name never does, so these four
    // cannot match an executable: they rely entirely on the friendly app name
    // being reported. That is fine while it is, and a silent gap if it is not,
    // which is worth stating rather than leaving to be rediscovered.
    expect(
      shouldCaptureFrame({
        ...capturable,
        appName: 'Unknown',
        processName: `${app.replace(/[^a-z0-9]/gi, '').toLowerCase()}.exe`
      })
    ).toEqual({ capture: true })

    expect(shouldCaptureFrame({ ...capturable, appName: app })).toEqual({
      capture: false,
      reason: 'excluded'
    })
  })

  it('has exactly four entries that depend on the app name', () => {
    expect(MULTI_TOKEN).toEqual([
      'Snipping Tool',
      'Snip & Sketch',
      'Proton Pass',
      'Keeper Password'
    ])
  })

  it('keeps every password manager in the list', () => {
    // Named individually because losing one is a privacy breach, and because a
    // list-driven test cannot notice a deletion.
    const lowered = BUILT_IN_EXCLUDED_APPS.map((a) => a.toLowerCase())
    for (const manager of [
      '1password',
      'bitwarden',
      'keepass',
      'lastpass',
      'dashlane',
      'nordpass',
      'proton pass',
      'keeper password',
      'roboform',
      'enpass'
    ]) {
      expect(lowered).toContain(manager)
    }
  })

  it('matches case-insensitively, as the exclusion is documented to', () => {
    expect(shouldCaptureFrame({ ...capturable, appName: '1PASSWORD' })).toEqual({
      capture: false,
      reason: 'excluded'
    })
    expect(shouldCaptureFrame({ ...capturable, appName: 'bitwarden' })).toEqual({
      capture: false,
      reason: 'excluded'
    })
  })

  it('does not exclude an ordinary app', () => {
    expect(shouldCaptureFrame({ ...capturable, appName: 'Notion' })).toEqual({ capture: true })
    expect(shouldCaptureFrame({ ...capturable, appName: 'Visual Studio Code' })).toEqual({
      capture: true
    })
    // The app list holds product names, not the bare word: an app merely called
    // "Password Generator" is captured. The window-TITLE list is what covers a
    // page about passwords, and it is tested separately below.
    expect(shouldCaptureFrame({ ...capturable, appName: 'Password Generator' })).toEqual({
      capture: true
    })
  })
})

// These are real apps that no one intended to exclude. They are excluded anyway,
// because the built-in list is matched as a case-insensitive SUBSTRING against
// the app and process name together, and two entries are short enough to
// appear inside unrelated names.
//
// The one that matters is Obsidian: `OBS` is a substring of it, so Rewind never
// records an Obsidian window. Omi ships an Obsidian export integration
// (`main/memoryExport/obsidian.ts`), so this is a product the app expects its
// users to have.
//
// These cases DOCUMENT the collisions rather than bless them. They are written
// so that fixing the list turns them red, which is the point: whoever narrows
// these entries should be told which behaviour they changed. Not fixed here
// deliberately, because the two failure directions are not symmetric — an
// over-exclusion means an app is not recorded, while a botched narrowing means
// a password manager IS recorded, and only someone who knows the real process
// names of OBS Studio and Loom on Windows can make that change safely.
describe('known over-exclusions from substring matching', () => {
  it.each([
    ['Obsidian', 'OBS'],
    ['Bloomberg Terminal', 'Loom'],
    ['Observer', 'OBS'],
    ['Jobs', 'OBS']
  ])('%s is excluded because the list contains %s', (app) => {
    expect(shouldCaptureFrame({ ...capturable, appName: app, processName: '' })).toEqual({
      capture: false,
      reason: 'excluded'
    })
  })

  it('excludes the tools those entries were meant for', () => {
    // The exclusions themselves are correct and must survive any narrowing.
    expect(shouldCaptureFrame({ ...capturable, appName: 'OBS Studio' })).toEqual({
      capture: false,
      reason: 'excluded'
    })
    expect(shouldCaptureFrame({ ...capturable, appName: 'Loom' })).toEqual({
      capture: false,
      reason: 'excluded'
    })
  })
})

describe('sensitive window-title markers', () => {
  it('has not silently shrunk', () => {
    expect(SENSITIVE_WINDOW_MARKERS).toHaveLength(12)
  })

  it.each(SENSITIVE_WINDOW_MARKERS)('never captures a window titled around %s', (marker) => {
    // The whole point of the title list: the app is an ordinary browser, so the
    // app-name list cannot help and only the title can.
    expect(
      shouldCaptureFrame({
        ...capturable,
        appName: 'Chrome',
        processName: 'chrome.exe',
        windowTitle: `Acme Bank — ${marker} — Google Chrome`
      })
    ).toEqual({ capture: false, reason: 'sensitive' })
  })

  it('matches a marker case-insensitively', () => {
    expect(shouldCaptureFrame({ ...capturable, windowTitle: 'ACME BANK LOGIN' })).toEqual({
      capture: false,
      reason: 'sensitive'
    })
  })

  it('keeps the markers that cover the common auth screens', () => {
    // Named individually for the same reason as the password managers: a
    // list-driven test cannot notice a deletion.
    for (const marker of ['password', 'login', 'sign in', '2fa', 'incognito', 'one-time code']) {
      expect(SENSITIVE_WINDOW_MARKERS).toContain(marker)
    }
  })

  it('captures an ordinary browser tab', () => {
    expect(
      shouldCaptureFrame({
        ...capturable,
        appName: 'Chrome',
        processName: 'chrome.exe',
        windowTitle: 'Quarterly report — Google Docs'
      })
    ).toEqual({ capture: true })
  })

  it('checks the title even when the app is not excluded', () => {
    // Ordering: the exclusion list runs first, so a sensitive title in an
    // ordinary app has to be caught by its own rule.
    expect(
      shouldCaptureFrame({
        ...capturable,
        appName: 'Firefox',
        processName: 'firefox.exe',
        windowTitle: 'Sign in to your account'
      })
    ).toEqual({ capture: false, reason: 'sensitive' })
  })
})
