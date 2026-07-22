import { describe, it, expect } from 'vitest'
import { isAllowedExternalScheme } from './externalUrl'

describe('isAllowedExternalScheme', () => {
  it('allows a scheme in the allow-list', () => {
    expect(isAllowedExternalScheme('https://omi.me', ['http', 'https'])).toBe(true)
    expect(isAllowedExternalScheme('http://omi.me', ['http', 'https'])).toBe(true)
    expect(isAllowedExternalScheme('mailto:hi@omi.me', ['http', 'https', 'mailto'])).toBe(true)
  })

  it('blocks a scheme not in the allow-list', () => {
    expect(isAllowedExternalScheme('mailto:hi@omi.me', ['http', 'https'])).toBe(false)
    expect(isAllowedExternalScheme('file:///etc/passwd', ['http', 'https'])).toBe(false)
    // UNC / custom-protocol handler abuse vectors.
    expect(isAllowedExternalScheme('\\\\evil\\share', ['http', 'https'])).toBe(false)
    expect(isAllowedExternalScheme('omi-agent://run', ['http', 'https'])).toBe(false)
  })

  it('blocks an unparseable URL', () => {
    expect(isAllowedExternalScheme('not a url', ['http', 'https'])).toBe(false)
    expect(isAllowedExternalScheme('', ['http', 'https'])).toBe(false)
  })
})
