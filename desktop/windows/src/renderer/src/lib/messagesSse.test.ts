import { describe, it, expect } from 'vitest'
import { parseMessagesSse, parseDoneMessage } from './messagesSse'

const b64 = (s: string): string => Buffer.from(s, 'utf-8').toString('base64')

describe('parseMessagesSse', () => {
  it('strips data: prefixes and concatenates chunks', () => {
    expect(parseMessagesSse('data: Hello\ndata:  world')).toBe('Hello world')
  })
  it('drops think: status events and done: markers', () => {
    const raw = 'data: think: Searching memories\ndata: Hi\ndone: 1'
    expect(parseMessagesSse(raw)).toBe('Hi')
  })
  it('drops message: side-frames without leaking their base64 into the text', () => {
    const raw = `data: Hi\nmessage: ${b64('{"id":"m","text":"side"}')}`
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

describe('parseDoneMessage', () => {
  it('decodes the base64 payload into the final message (server id + stripped text)', () => {
    const payload = {
      id: 'srv-1',
      text: 'The answer.', // backend already stripped [n] markers
      memories: [
        {
          id: 'conv-a',
          structured: { title: 'Standup', emoji: '📝' },
          created_at: '2026-07-13T00:00:00Z'
        }
      ],
      chart_data: null,
      ask_for_nps: true
    }
    const done = parseDoneMessage(`done: ${b64(JSON.stringify(payload))}`)
    expect(done).toEqual({
      id: 'srv-1',
      text: 'The answer.',
      citations: [{ id: 'conv-a', title: 'Standup', emoji: '📝' }],
      chartData: undefined,
      askForNps: true
    })
  })

  it('carries chart_data through opaquely and defaults ask_for_nps to false', () => {
    const chart = { chart_type: 'bar', title: 'T', datasets: [] }
    const done = parseDoneMessage(
      `done: ${b64(JSON.stringify({ id: 'm', text: 'x', chart_data: chart }))}`
    )
    expect(done?.chartData).toEqual(chart)
    expect(done?.askForNps).toBe(false)
    expect(done?.citations).toEqual([])
  })

  it('returns null for a non-done line or an undecodable payload (never throws)', () => {
    expect(parseDoneMessage('data: hello')).toBeNull()
    expect(parseDoneMessage('done:')).toBeNull()
    expect(parseDoneMessage('done: @@@not-base64-json@@@')).toBeNull()
    expect(parseDoneMessage(`done: ${b64('not json')}`)).toBeNull()
  })

  it('is untouched by parseMessagesSse (which still drops done: frames)', () => {
    const raw = `data: Hi\ndone: ${b64(JSON.stringify({ id: 'm', text: 'Hi' }))}`
    expect(parseMessagesSse(raw)).toBe('Hi')
  })
})
