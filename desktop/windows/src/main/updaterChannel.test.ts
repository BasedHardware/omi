import { describe, it, expect } from 'vitest'
import { betaOptInToAllowPrerelease, resolveBetaChannelChange } from './updaterChannel'

describe('updaterChannel', () => {
  it('maps the beta opt-in straight onto allowPrerelease', () => {
    expect(betaOptInToAllowPrerelease(true)).toBe(true)
    expect(betaOptInToAllowPrerelease(false)).toBe(false)
    // Only an explicit true opts in — a junk/undefined value stays stable.
    expect(betaOptInToAllowPrerelease(undefined as never)).toBe(false)
  })

  it('flags a real opt-in change and no-ops when the lever is unchanged', () => {
    // Off → On: apply prerelease and re-check.
    expect(resolveBetaChannelChange(false, true)).toEqual({ allowPrerelease: true, changed: true })
    // On → Off: back to stable, re-check.
    expect(resolveBetaChannelChange(true, false)).toEqual({ allowPrerelease: false, changed: true })
    // Unchanged (an unrelated settings write): don't touch the updater or re-check.
    expect(resolveBetaChannelChange(false, false)).toEqual({
      allowPrerelease: false,
      changed: false
    })
    expect(resolveBetaChannelChange(true, true)).toEqual({ allowPrerelease: true, changed: false })
  })
})
