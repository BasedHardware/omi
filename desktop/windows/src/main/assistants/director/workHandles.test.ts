import { describe, it, expect } from 'vitest'
import {
  canonicalizeUrl,
  canonicalizeFile,
  primaryHandle,
  isDurable,
  handleIdentityKey,
  appWindowHandleValue
} from './workHandles'

describe('canonicalizeUrl', () => {
  it('accepts only http/https and lowercases the host', () => {
    expect(canonicalizeUrl('HTTPS://GitHub.COM/acme')).toBe('https://github.com/acme')
    expect(canonicalizeUrl('ftp://example.com/x')).toBeNull()
    expect(canonicalizeUrl('not a url')).toBeNull()
  })

  it('strips default ports and keeps explicit non-default ports', () => {
    expect(canonicalizeUrl('https://example.com:443/a')).toBe('https://example.com/a')
    expect(canonicalizeUrl('http://example.com:80/a')).toBe('http://example.com/a')
    expect(canonicalizeUrl('https://example.com:8443/a')).toBe('https://example.com:8443/a')
  })

  it('strips the trailing slash only when a path exists', () => {
    expect(canonicalizeUrl('https://example.com/docs/')).toBe('https://example.com/docs')
    expect(canonicalizeUrl('https://example.com/')).toBe('https://example.com/')
  })

  it('drops tracking and secret query params while keeping the rest in order', () => {
    expect(canonicalizeUrl('https://example.com/a?utm_source=x&page=2&access_token=s&q=hi')).toBe(
      'https://example.com/a?page=2&q=hi'
    )
    expect(canonicalizeUrl('https://example.com/a?mysessionid=1&x_sig=2&keep=3')).toBe(
      'https://example.com/a?keep=3'
    )
  })
})

describe('canonicalizeFile', () => {
  it('normalizes separators and rejects empty and roots', () => {
    expect(canonicalizeFile('C:/Users/zach/notes.txt')).toBe('C:\\Users\\zach\\notes.txt')
    expect(canonicalizeFile('')).toBeNull()
    expect(canonicalizeFile('\\')).toBeNull()
    expect(canonicalizeFile('C:\\')).toBeNull()
  })
})

describe('handle identity', () => {
  it('durable = url or file; identityKey is kind::value', () => {
    expect(isDurable({ kind: 'url', value: 'https://a.com/x' })).toBe(true)
    expect(isDurable({ kind: 'file', value: 'C:\\a' })).toBe(true)
    expect(isDurable({ kind: 'app_window', value: 'App\nTitle' })).toBe(false)
    expect(handleIdentityKey({ kind: 'url', value: 'https://a.com/x' })).toBe(
      'url::https://a.com/x'
    )
  })

  it('primaryHandle prefers the first durable handle, else the first', () => {
    const appWindow = { kind: 'app_window' as const, value: 'App\nT' }
    const url = { kind: 'url' as const, value: 'https://a.com/x' }
    expect(primaryHandle([appWindow, url])).toEqual(url)
    expect(primaryHandle([appWindow])).toEqual(appWindow)
    expect(primaryHandle([])).toBeNull()
  })

  it('app_window handle value is app newline title', () => {
    expect(appWindowHandleValue('Code', 'main.ts')).toBe('Code\nmain.ts')
  })
})
