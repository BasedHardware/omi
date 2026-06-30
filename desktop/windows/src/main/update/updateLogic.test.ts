import { describe, it, expect } from 'vitest'
import { shouldCheckForUpdates } from './updateLogic'

const PACKAGED = { isDev: false, isPackaged: true, isBench: false }

describe('shouldCheckForUpdates', () => {
  it('checks from a real packaged build', () => {
    expect(shouldCheckForUpdates(PACKAGED)).toBe(true)
  })

  it('never checks in dev', () => {
    expect(shouldCheckForUpdates({ ...PACKAGED, isDev: true })).toBe(false)
  })

  it('never checks from an unpacked build', () => {
    expect(shouldCheckForUpdates({ ...PACKAGED, isPackaged: false })).toBe(false)
  })

  it('never checks during a bench run, even if packaged', () => {
    expect(shouldCheckForUpdates({ ...PACKAGED, isBench: true })).toBe(false)
  })
})
