import { describe, it, expect } from 'vitest'
import { contentTypeFor, requestToRelPath } from './renderServerLogic'

describe('requestToRelPath', () => {
  it('maps root to index.html', () => {
    expect(requestToRelPath('/')).toBe('index.html')
    expect(requestToRelPath('')).toBe('index.html')
  })

  it('returns asset paths under the root', () => {
    expect(requestToRelPath('/assets/index-abc.js')).toBe('assets/index-abc.js')
  })

  it('strips query strings and hashes', () => {
    expect(requestToRelPath('/index.html?v=1')).toBe('index.html')
    expect(requestToRelPath('/assets/x.css#frag')).toBe('assets/x.css')
  })

  it('blocks path traversal out of the root', () => {
    expect(requestToRelPath('/../../etc/passwd')).toBe('etc/passwd')
    expect(requestToRelPath('/..%2f..%2fsecret')).toBe('secret')
  })

  it('percent-decodes', () => {
    expect(requestToRelPath('/assets/a%20b.png')).toBe('assets/a b.png')
  })
})

describe('contentTypeFor', () => {
  it('knows common web asset types', () => {
    expect(contentTypeFor('app.js')).toBe('text/javascript')
    expect(contentTypeFor('app.css')).toBe('text/css')
    expect(contentTypeFor('index.html')).toBe('text/html')
    expect(contentTypeFor('font.woff2')).toBe('font/woff2')
  })

  it('falls back to octet-stream for unknown types', () => {
    expect(contentTypeFor('mystery.xyz')).toBe('application/octet-stream')
  })
})
