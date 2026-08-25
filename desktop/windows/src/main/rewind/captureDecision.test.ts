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
    expect(shouldCaptureFrame({ ...base, locked: true })).toEqual({ capture: false, reason: 'locked' })
  })
  it('skips when the user is idle past the threshold', () => {
    expect(shouldCaptureFrame({ ...base, idleSeconds: 120 })).toEqual({ capture: false, reason: 'idle' })
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
    expect(
      shouldCaptureFrame({ ...base, appName: 'Notepad', excludedApps: ['chrome'] })
    ).toEqual({ capture: true })
  })
  it('skips a login page by window title (sensitive)', () => {
    expect(
      shouldCaptureFrame({ ...base, appName: 'Google Chrome', windowTitle: 'Sign in - Google Accounts' })
    ).toEqual({ capture: false, reason: 'sensitive' })
  })
  it('skips an incognito window by title (sensitive)', () => {
    expect(
      shouldCaptureFrame({ ...base, appName: 'Google Chrome', windowTitle: 'New Tab - Google Chrome (Incognito)' })
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
    expect(
      shouldCaptureFrame({ ...base, lastHash: base.hash, lastCapturedAtMs: null })
    ).toEqual({ capture: true })
  })
})
