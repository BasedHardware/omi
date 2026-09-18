import { describe, it, expect } from 'vitest'
import { shouldCaptureFrame, DUP_HAMMING_THRESHOLD, KEYFRAME_ANCHOR_MS } from './captureDecision'

const base = {
  locked: false,
  idleSeconds: 0,
  idleThresholdSeconds: 60,
  busy: false,
  appName: 'Code.exe',
  excludedApps: [] as string[],
  hash: '1111000011110000',
  lastHash: '0000111100001111', // very different
  nowMs: 1_000_000,
  lastCapturedAtMs: 995_000 // 5s ago — inside the keyframe window
}

describe('shouldCaptureFrame', () => {
  it('captures a normal, changed frame', () => {
    expect(shouldCaptureFrame(base)).toEqual({ capture: true })
  })
  it('skips when the screen is locked', () => {
    expect(shouldCaptureFrame({ ...base, locked: true })).toEqual({
      capture: false,
      reason: 'locked'
    })
  })
  it('skips when the user is idle past the threshold', () => {
    expect(shouldCaptureFrame({ ...base, idleSeconds: 120 })).toEqual({
      capture: false,
      reason: 'idle'
    })
  })
  it('skips when a previous frame is still processing', () => {
    expect(shouldCaptureFrame({ ...base, busy: true })).toEqual({ capture: false, reason: 'busy' })
  })
  it('skips when the focused app is excluded (case-insensitive)', () => {
    expect(shouldCaptureFrame({ ...base, excludedApps: ['code.exe'] })).toEqual({
      capture: false,
      reason: 'excluded'
    })
  })
  it('excludes by case-insensitive substring of the app name', () => {
    expect(
      shouldCaptureFrame({ ...base, appName: 'Google Chrome', excludedApps: ['chrome'] })
    ).toEqual({ capture: false, reason: 'excluded' })
  })
  it('excludes by substring of the process name', () => {
    expect(
      shouldCaptureFrame({
        ...base,
        appName: 'Some App',
        processName: 'chrome',
        excludedApps: ['chrome']
      })
    ).toEqual({ capture: false, reason: 'excluded' })
  })
  it('ignores empty/whitespace exclusion entries', () => {
    expect(shouldCaptureFrame({ ...base, excludedApps: ['', '  '] })).toEqual({ capture: true })
  })
  it('does not exclude an unrelated app', () => {
    expect(shouldCaptureFrame({ ...base, appName: 'Notepad', excludedApps: ['chrome'] })).toEqual({
      capture: true
    })
  })
  it('skips a login page by window title (sensitive)', () => {
    expect(
      shouldCaptureFrame({
        ...base,
        appName: 'Google Chrome',
        windowTitle: 'Sign in - Google Accounts'
      })
    ).toEqual({ capture: false, reason: 'sensitive' })
  })
  it('skips an incognito window by title (sensitive)', () => {
    expect(
      shouldCaptureFrame({
        ...base,
        appName: 'Google Chrome',
        windowTitle: 'New Tab - Google Chrome (Incognito)'
      })
    ).toEqual({ capture: false, reason: 'sensitive' })
  })
  it('skips a password page by title (sensitive)', () => {
    expect(
      shouldCaptureFrame({ ...base, appName: 'Firefox', windowTitle: 'Change your password' })
    ).toEqual({ capture: false, reason: 'sensitive' })
  })
  it('captures a normal browser tab', () => {
    expect(
      shouldCaptureFrame({ ...base, appName: 'Google Chrome', windowTitle: 'Wikipedia — Octopus' })
    ).toEqual({ capture: true })
  })
  it('skips a near-duplicate of the last frame within the keyframe window', () => {
    expect(shouldCaptureFrame({ ...base, lastHash: base.hash })).toEqual({
      capture: false,
      reason: 'duplicate'
    })
  })
  it('captures when difference exceeds the dedup threshold', () => {
    // flip more than DUP_HAMMING_THRESHOLD bits
    const flipped = base.hash.split('')
    for (let i = 0; i <= DUP_HAMMING_THRESHOLD; i++) flipped[i] = flipped[i] === '1' ? '0' : '1'
    expect(shouldCaptureFrame({ ...base, lastHash: flipped.join('') })).toEqual({ capture: true })
  })
  // --- Keyframe anchor (Mac frameDedupeMaxInterval = 30s) ---
  it('skips an identical frame within 30s of the last stored frame', () => {
    expect(
      shouldCaptureFrame({
        ...base,
        lastHash: base.hash,
        nowMs: 1_000_000,
        lastCapturedAtMs: 1_000_000 - (KEYFRAME_ANCHOR_MS - 1_000) // 29s ago
      })
    ).toEqual({ capture: false, reason: 'duplicate' })
  })
  it('force-captures an identical frame past 30s as a periodic anchor', () => {
    expect(
      shouldCaptureFrame({
        ...base,
        lastHash: base.hash,
        nowMs: 1_000_000,
        lastCapturedAtMs: 1_000_000 - (KEYFRAME_ANCHOR_MS + 1_000) // 31s ago
      })
    ).toEqual({ capture: true })
  })
  it('captures the first-ever frame even if the hash matches (nothing stored yet)', () => {
    expect(shouldCaptureFrame({ ...base, lastHash: base.hash, lastCapturedAtMs: null })).toEqual({
      capture: true
    })
  })
})

/** A hash differing from `base.hash` in exactly `bits` positions. */
function hashDifferingBy(bits: number): string {
  const chars = base.hash.split('')
  for (let i = 0; i < bits; i++) chars[i] = chars[i] === '1' ? '0' : '1'
  return chars.join('')
}

// Every case above sits comfortably PAST the boundary it exercises: idle at 120
// against a threshold of 60, "very different" against identical, 29s and 31s
// against a 30s window. None of them sits ON the boundary, so each of these
// three comparisons could be flipped by one step and the suite stayed green. A
// mutation audit confirmed all three.
//
// The boundary matters to a user in each case: whether a frame is recorded at
// the instant they go idle, whether a screen that changed by a hair is stored
// again, and whether a static screen still gets its periodic anchor.
//
// The distances and durations below are written as LITERALS rather than derived
// from the constants they bracket. Deriving them looks tidier and cannot fail:
// the first version of this block built its fixtures with
// `hashDifferingBy(DUP_HAMMING_THRESHOLD)`, so zeroing that constant moved the
// fixture with it and the assertion still passed. A boundary test has to state
// the boundary.
describe('shouldCaptureFrame boundaries', () => {
  describe('the idle threshold', () => {
    it('does not capture at exactly the threshold', () => {
      // `>=`: the threshold second is already idle. One step to `>` and Rewind
      // takes one more frame after the user has walked away.
      expect(shouldCaptureFrame({ ...base, idleSeconds: 60, idleThresholdSeconds: 60 })).toEqual({
        capture: false,
        reason: 'idle'
      })
    })

    it('captures one second before the threshold', () => {
      expect(shouldCaptureFrame({ ...base, idleSeconds: 59, idleThresholdSeconds: 60 })).toEqual({
        capture: true
      })
    })
  })

  describe('the duplicate-frame threshold', () => {
    // macOS measured the scale this rides on and recorded it in
    // `RewindOCRService.swift` (`dedupThreshold`): "spinner animation = 1,
    // cursor shift = 4, real content change = 23". A distance of 4 is a cursor
    // moving, which is the same screen; 5 is where Windows starts storing again.
    it('treats a frame four bits away as the same screen', () => {
      expect(shouldCaptureFrame({ ...base, lastHash: hashDifferingBy(4) })).toEqual({
        capture: false,
        reason: 'duplicate'
      })
    })

    it('captures a frame five bits away', () => {
      expect(shouldCaptureFrame({ ...base, lastHash: hashDifferingBy(5) })).toEqual({
        capture: true
      })
    })

    it('pins the threshold itself, which the cases above cannot', () => {
      // Those two bracket the CURRENT value; only this notices it moving. Worth
      // a line of its own because macOS uses 5 where Windows uses 4, so the two
      // platforms disagree about a screen that changed by exactly five bits.
      expect(DUP_HAMMING_THRESHOLD).toBe(4)
    })

    it('still captures a near-duplicate once the anchor window has passed', () => {
      // The two rules compose: the dedup threshold only suppresses a frame
      // while the anchor window is open.
      expect(
        shouldCaptureFrame({
          ...base,
          lastHash: hashDifferingBy(4),
          nowMs: 1_000_000,
          lastCapturedAtMs: 1_000_000 - 30_001
        })
      ).toEqual({ capture: true })
    })
  })

  describe('the keyframe anchor window', () => {
    it('suppresses a duplicate at exactly thirty seconds', () => {
      // `<=`: at exactly 30s the last stored frame is still the anchor. macOS
      // uses the same comparison against the same value
      // (`RewindIndexer.swift:218`, `<= frameDedupeMaxInterval`).
      expect(
        shouldCaptureFrame({
          ...base,
          lastHash: base.hash,
          nowMs: 1_000_000,
          lastCapturedAtMs: 1_000_000 - 30_000
        })
      ).toEqual({ capture: false, reason: 'duplicate' })
    })

    it('anchors one millisecond past thirty seconds', () => {
      expect(
        shouldCaptureFrame({
          ...base,
          lastHash: base.hash,
          nowMs: 1_000_000,
          lastCapturedAtMs: 1_000_000 - 30_001
        })
      ).toEqual({ capture: true })
    })

    it('pins the window to the value macOS sets', () => {
      // `frameDedupeMaxInterval: TimeInterval = 30.0`, RewindIndexer.swift:36.
      expect(KEYFRAME_ANCHOR_MS).toBe(30_000)
    })
  })
})
