import { describe, it, expect } from 'vitest'
import { scrubEmails, scrubEventPii } from './sentryScrub'

describe('scrubEmails', () => {
  it('replaces an email with a placeholder', () => {
    expect(scrubEmails('failed for chris.demian@gmail.com while syncing')).toBe(
      'failed for [email] while syncing'
    )
  })

  it('replaces every email in the string', () => {
    expect(scrubEmails('a@b.co and c.d@e-f.io')).toBe('[email] and [email]')
  })

  it('leaves email-free text untouched', () => {
    expect(scrubEmails('database timeout after 30s')).toBe('database timeout after 30s')
  })
})

describe('scrubEventPii', () => {
  it('scrubs the message and exception values', () => {
    const event = {
      message: 'login failed for user@example.com',
      exception: {
        values: [{ value: 'token for admin@corp.io rejected' }, { value: 'no pii here' }]
      }
    }
    const out = scrubEventPii(event)
    expect(out.message).toBe('login failed for [email]')
    expect(out.exception.values[0].value).toBe('token for [email] rejected')
    expect(out.exception.values[1].value).toBe('no pii here')
  })

  it('handles an event with no message or exception', () => {
    expect(() => scrubEventPii({})).not.toThrow()
  })
})
