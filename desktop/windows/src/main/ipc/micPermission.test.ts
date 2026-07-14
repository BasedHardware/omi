// The mic step's honesty rests entirely on this parse: onboarding used to read
// `navigator.permissions.query({name:'microphone'})`, which Electron answers 'granted'
// unconditionally, so a brand-new profile with the mic BLOCKED by Windows sailed through
// the step without ever calling getUserMedia. The registry is the real answer — and an
// absent key must never read as a grant.
import { describe, it, expect } from 'vitest'
import { parseConsentValue, resolveMicState } from './micPermission'

// Verbatim `reg.exe query … /v Value` output (blank first line, tab-ish padding).
const regOutput = (value: string): string =>
  `\r\nHKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone\r\n    Value    REG_SZ    ${value}\r\n\r\n`

describe('parseConsentValue', () => {
  it('pulls the consent value out of reg.exe output', () => {
    expect(parseConsentValue(regOutput('Allow'))).toBe('Allow')
    expect(parseConsentValue(regOutput('Deny'))).toBe('Deny')
  })

  it('returns null when the value is absent (key never written)', () => {
    expect(parseConsentValue('')).toBeNull()
    expect(
      parseConsentValue('ERROR: The system was unable to find the specified registry key')
    ).toBeNull()
  })
})

describe('resolveMicState', () => {
  it('grants only on an explicit Allow', () => {
    expect(resolveMicState('Allow', 'Allow')).toBe('granted')
    expect(resolveMicState('Allow', null)).toBe('granted')
  })

  it('denies when EITHER the master toggle or the desktop-app toggle says Deny', () => {
    expect(resolveMicState('Deny', 'Allow')).toBe('denied')
    expect(resolveMicState('Allow', 'Deny')).toBe('denied')
    expect(resolveMicState('Deny', 'Deny')).toBe('denied')
  })

  // THE REGRESSION: an unset permission is not a granted one. Reporting 'unknown' is what
  // keeps the step from auto-skipping on a fresh profile.
  it('reports unknown — never granted — when the consent was never recorded', () => {
    expect(resolveMicState(null, null)).toBe('unknown')
    expect(resolveMicState(null, 'Allow')).toBe('unknown')
  })
})
