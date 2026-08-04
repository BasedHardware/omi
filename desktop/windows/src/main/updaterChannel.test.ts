import { describe, it, expect } from 'vitest'
import { betaOptInToUpdateChannel, resolveBetaChannelChange } from './updaterChannel'

describe('updaterChannel', () => {
  it('maps only an explicit beta opt-in to the beta channel', () => {
    expect(betaOptInToUpdateChannel(true)).toBe('beta')
    expect(betaOptInToUpdateChannel(false)).toBe('stable')
    expect(betaOptInToUpdateChannel(undefined as never)).toBe('stable')
  })

  it('flags a real channel move and ignores unrelated settings writes', () => {
    expect(resolveBetaChannelChange('stable', true)).toEqual({
      channel: 'beta',
      changed: true
    })
    expect(resolveBetaChannelChange('beta', false)).toEqual({
      channel: 'stable',
      changed: true
    })
    expect(resolveBetaChannelChange('stable', false)).toEqual({
      channel: 'stable',
      changed: false
    })
    expect(resolveBetaChannelChange('beta', true)).toEqual({
      channel: 'beta',
      changed: false
    })
  })
})
