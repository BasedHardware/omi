import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import {
  setCurrentScreen,
  getCurrentScreen,
  currentScreenAgeMs,
  screenCacheFresh,
  reaffirmCurrentScreen,
  CACHE_FRESH_MS
} from './currentScreen'

describe('currentScreen cache', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Reset to a known state for each test.
    setCurrentScreen('')
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('stores and returns the latest text', () => {
    setCurrentScreen('hello world')
    expect(getCurrentScreen().text).toBe('hello world')
  })

  it('overwrites with the newest text', () => {
    setCurrentScreen('first')
    setCurrentScreen('second')
    expect(getCurrentScreen().text).toBe('second')
  })

  it('stamps the time on set, so age reflects how stale the text is', () => {
    vi.setSystemTime(new Date('2026-06-09T00:00:00Z'))
    setCurrentScreen('on screen')
    vi.advanceTimersByTime(1500)
    expect(currentScreenAgeMs()).toBe(1500)
  })
})

describe('screenCacheFresh', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.resetModules()
  })

  it('is false before any setCurrentScreen (ts === 0)', async () => {
    // Fresh module so the cache has never been seeded this "session" (ts === 0).
    vi.resetModules()
    const mod = await import('./currentScreen')
    expect(mod.screenCacheFresh(Date.now())).toBe(false)
  })

  it('is true right after setCurrentScreen', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-09T00:00:00Z'))
    setCurrentScreen('on screen')
    expect(screenCacheFresh(Date.now())).toBe(true)
  })

  it('is false once the age exceeds CACHE_FRESH_MS', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-09T00:00:00Z'))
    setCurrentScreen('on screen')
    vi.advanceTimersByTime(CACHE_FRESH_MS + 1)
    expect(screenCacheFresh(Date.now())).toBe(false)
  })

  it('is true exactly at the CACHE_FRESH_MS boundary', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-09T00:00:00Z'))
    setCurrentScreen('on screen')
    vi.advanceTimersByTime(CACHE_FRESH_MS)
    expect(screenCacheFresh(Date.now())).toBe(true)
  })
})

describe('reaffirmCurrentScreen', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-09T00:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.resetModules()
  })

  it('keeps the same text but bumps freshness (screen unchanged → still current)', () => {
    setCurrentScreen('on screen')
    vi.advanceTimersByTime(CACHE_FRESH_MS - 1000)
    reaffirmCurrentScreen()
    // Text is untouched...
    expect(getCurrentScreen().text).toBe('on screen')
    // ...but the cache is freshly stamped, so age resets toward zero.
    expect(currentScreenAgeMs()).toBe(0)
  })

  it('is a no-op when the cache was never seeded this session (ts === 0)', async () => {
    vi.resetModules()
    const mod = await import('./currentScreen')
    mod.reaffirmCurrentScreen()
    expect(mod.screenCacheFresh(Date.now())).toBe(false)
  })

  // Regression for Bug #4: a screen held static streams only "duplicate" frames,
  // which never re-OCR. Without re-affirming on each duplicate, the cache ages out
  // at CACHE_FRESH_MS and the chat stops being able to read an unchanged screen.
  it('keeps a static screen readable past CACHE_FRESH_MS when duplicates re-affirm it', () => {
    setCurrentScreen('static article text')
    // Simulate ~2× the freshness window of duplicate frames arriving every second,
    // each one re-affirming the unchanged screen.
    for (let elapsed = 0; elapsed < CACHE_FRESH_MS * 2; elapsed += 1000) {
      vi.advanceTimersByTime(1000)
      reaffirmCurrentScreen()
      expect(screenCacheFresh(Date.now())).toBe(true)
    }
    expect(getCurrentScreen().text).toBe('static article text')
  })

  // The cache must still go stale when there is NO confirming signal at all
  // (capture paused on idle/lock/excluded) — i.e. re-affirm is the only thing
  // holding it fresh, not an unconditional extension.
  it('still goes stale if nothing re-affirms it', () => {
    setCurrentScreen('static article text')
    vi.advanceTimersByTime(CACHE_FRESH_MS + 1)
    expect(screenCacheFresh(Date.now())).toBe(false)
  })
})
