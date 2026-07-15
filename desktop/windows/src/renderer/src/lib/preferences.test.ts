// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest'
import { getPreferences, setPreferences, onPreferencesChange } from './preferences'

// The bar's typed submit passes `fromVoice = !!getPreferences().floatingBarTypedVoiceEnabled`
// (BarApp). These assert that exact value flips with the additive preference.
describe('floatingBarTypedVoiceEnabled — speak typed bar replies toggle', () => {
  beforeEach(() => {
    localStorage.clear()
    setPreferences({}) // reload the module cache from the cleared store → defaults
  })

  it('defaults off — a typed bar submit passes fromVoice=false', () => {
    expect(!!getPreferences().floatingBarTypedVoiceEnabled).toBe(false)
  })

  it('when enabled, a typed bar submit passes fromVoice=true (and notifies subscribers)', () => {
    let observed: boolean | undefined
    const off = onPreferencesChange((p) => {
      observed = !!p.floatingBarTypedVoiceEnabled
    })
    setPreferences({ floatingBarTypedVoiceEnabled: true })
    expect(!!getPreferences().floatingBarTypedVoiceEnabled).toBe(true)
    expect(observed).toBe(true)
    off()
  })

  it('is additive — enabling it leaves other preferences intact', () => {
    setPreferences({ language: 'es', floatingBarTypedVoiceEnabled: true })
    expect(getPreferences().language).toBe('es')
    expect(getPreferences().floatingBarTypedVoiceEnabled).toBe(true)
  })
})
