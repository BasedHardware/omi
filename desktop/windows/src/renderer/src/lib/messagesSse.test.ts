import { describe, it, expect } from 'vitest'
import { parseMessagesSse } from './messagesSse'

describe('parseMessagesSse', () => {
  it('strips data: prefixes and concatenates chunks', () => {
    expect(parseMessagesSse('data: Hello\ndata:  world')).toBe('Hello world')
  })
  it('drops think: status events and done: markers', () => {
    const raw = 'data: think: Searching memories\ndata: Hi\ndone: 1'
    expect(parseMessagesSse(raw)).toBe('Hi')
  })
  it('restores __CRLF__ tokens to newlines', () => {
    expect(parseMessagesSse('data: line1__CRLF__line2')).toBe('line1\nline2')
  })
  it('reconstructs a JSON plan split across chunks (planner use case)', () => {
    const raw = 'data: {"id":"p1",\ndata: "summary":"x","targetWindow":"W",\ndata: "steps":[]}'
    expect(parseMessagesSse(raw)).toBe('{"id":"p1","summary":"x","targetWindow":"W","steps":[]}')
  })
})
