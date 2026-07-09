import { describe, it, expect } from 'vitest'
import { parseOmiSseLine, OmiSseAccumulator } from './omiSse'

describe('parseOmiSseLine', () => {
  it('strips the data: prefix (with and without the space)', () => {
    expect(parseOmiSseLine('data: hello')).toBe('hello')
    expect(parseOmiSseLine('data:hello')).toBe('hello')
  })

  it('drops empty lines and the done: terminator', () => {
    expect(parseOmiSseLine('')).toBeNull()
    expect(parseOmiSseLine('done: eyJmb28iOiJiYXIifQ==')).toBeNull()
  })

  it('drops ephemeral think: status events', () => {
    expect(parseOmiSseLine('data: think: Searching memories')).toBeNull()
  })

  it('restores __CRLF__ newline tokens', () => {
    expect(parseOmiSseLine('data: line one__CRLF__line two')).toBe('line one\nline two')
  })

  it('passes through bare content lines unchanged', () => {
    expect(parseOmiSseLine('plain chunk')).toBe('plain chunk')
  })
})

describe('OmiSseAccumulator', () => {
  it('accumulates reply text across chunks that split lines arbitrarily', () => {
    const acc = new OmiSseAccumulator()
    acc.feed('data: Hel')
    expect(acc.text).toBe('') // line not terminated yet
    acc.feed('lo\ndata: think: Searching memories\ndata:  world\n')
    expect(acc.text).toBe('Hello world')
    acc.feed('done: eyJ9\n')
    expect(acc.end()).toBe('')
    expect(acc.text).toBe('Hello world')
  })

  it('end() flushes a trailing unterminated content line', () => {
    const acc = new OmiSseAccumulator()
    acc.feed('data: tail without newline')
    expect(acc.text).toBe('')
    expect(acc.end()).toBe('tail without newline')
    expect(acc.text).toBe('tail without newline')
  })
})
