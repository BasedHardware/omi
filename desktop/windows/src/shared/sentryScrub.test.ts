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

  it('drops URL queries and scrubs breadcrumbs, extra fields, and secret keys', () => {
    const event = {
      request: {
        url: 'https://api.omi.me/callback?code=secret#done',
        query_string: 'code=secret',
        headers: { authorization: 'Bearer token', Accept: 'application/json' }
      },
      breadcrumbs: [
        {
          message: 'signed in as ada@example.com',
          data: { url: 'https://example.com/path?state=secret' }
        }
      ],
      extra: {
        owner: 'ada@example.com',
        nested: { api_key: 'sk-secret' }
      }
    }
    const out = scrubEventPii(event)
    expect(out.request.url).toBe('https://api.omi.me/callback')
    expect(out.request).not.toHaveProperty('query_string')
    expect(out.request.headers.authorization).toBe('[redacted]')
    expect(out.breadcrumbs[0].message).toBe('signed in as [email]')
    expect(out.breadcrumbs[0].data.url).toBe('https://example.com/path')
    expect(out.extra.owner).toBe('[email]')
    expect(out.extra.nested.api_key).toBe('[redacted]')
  })
})
