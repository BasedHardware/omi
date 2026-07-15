// The mic step's honesty rests entirely on this parse: onboarding used to read
// `navigator.permissions.query({name:'microphone'})`, which Electron answers 'granted'
// unconditionally, so a brand-new profile with the mic BLOCKED by Windows sailed through
// the step without ever calling getUserMedia. The registry is the real answer — and an
// absent key must never read as a grant.
import { describe, it, expect, afterEach } from 'vitest'
import { parseConsentValue, resolveMicState, readMicPermissionState } from './micPermission'

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

// The E2E drives the mic state through this seam rather than stubbing
// `navigator.permissions` — stubbing that API is what let the old spec stay green while
// the step false-granted on every run. The seam must never open in a shipped app.
describe('readMicPermissionState — E2E seam', () => {
  afterEach(() => {
    delete process.env.OMI_E2E
    delete process.env.OMI_E2E_MIC_STATE
  })

  it('honors OMI_E2E_MIC_STATE under OMI_E2E', async () => {
    process.env.OMI_E2E = '1'
    for (const state of ['granted', 'denied', 'unknown'] as const) {
      process.env.OMI_E2E_MIC_STATE = state
      expect(await readMicPermissionState()).toBe(state)
    }
  })

  it('IGNORES the override when OMI_E2E is not set — the shipped app always reads the OS', async () => {
    process.env.OMI_E2E_MIC_STATE = 'granted'
    // No OMI_E2E: falls through to the real registry read (or 'unknown' off-Windows).
    // The one thing that must never happen is the env var being taken at face value on a
    // machine where Windows actually denies the mic.
    const state = await readMicPermissionState()
    expect(['granted', 'denied', 'unknown']).toContain(state)
    if (process.platform !== 'win32') expect(state).toBe('unknown')
  })

  it('rejects a junk override rather than trusting it', async () => {
    process.env.OMI_E2E = '1'
    process.env.OMI_E2E_MIC_STATE = 'yes-please'
    const state = await readMicPermissionState()
    expect(state).not.toBe('yes-please')
  })
})
