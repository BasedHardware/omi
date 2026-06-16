import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import {
  setCurrentScreen,
  getCurrentScreen,
  currentScreenAgeMs,
  screenCacheFresh,
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
