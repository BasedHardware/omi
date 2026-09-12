import { describe, expect, it } from 'vitest'
import { parseRewindNaturalSearch } from './rewindNaturalSearch'

const NOW = new Date(2026, 6, 31, 14, 30)

describe('parseRewindNaturalSearch', () => {
  it('scopes yesterday and leaves searchable words', () => {
    const parsed = parseRewindNaturalSearch('What was on my screen: invoice yesterday?', NOW)
    const yesterday = new Date(2026, 6, 30)
    yesterday.setHours(0, 0, 0, 0)
    expect(parsed).toEqual({
      query: 'invoice',
      from: yesterday.getTime(),
      to: yesterday.getTime() + 86_399_999
    })
  })

  it('makes a time-only question browse the matching period', () => {
    const parsed = parseRewindNaturalSearch('What was on my screen this morning?', NOW)
    const morning = new Date(NOW)
    morning.setHours(6, 0, 0, 0)
    expect(parsed).toEqual({
      query: '',
      from: morning.getTime(),
      to: morning.getTime() + 21_599_999
    })
  })

  it('treats activity questions as time-only searches', () => {
    const parsed = parseRewindNaturalSearch('What did I do yesterday?', NOW)
    expect(parsed.query).toBe('')
  })

  it('treats gerund activity questions as time-only searches', () => {
    expect(parseRewindNaturalSearch('What was I doing yesterday?', NOW).query).toBe('')
  })

  it('strips leading delimiters before matching question framing', () => {
    expect(parseRewindNaturalSearch('Yesterday, what was I doing?', NOW).query).toBe('')
    expect(parseRewindNaturalSearch('Yesterday — what happened?', NOW).query).toBe('')
  })

  it('treats working activity questions as time-only searches', () => {
    expect(parseRewindNaturalSearch('What was I working on yesterday?', NOW).query).toBe('')
  })

  it('treats happened questions as time-only searches', () => {
    expect(parseRewindNaturalSearch('What happened yesterday?', NOW).query).toBe('')
    expect(parseRewindNaturalSearch('what happens today', NOW).query).toBe('')
  })

  it('treats contractions in time-only questions as boilerplate', () => {
    expect(parseRewindNaturalSearch("What's on my screen today?", NOW).query).toBe('')
  })

  it('keeps combined relative dates and day parts in one scope', () => {
    const parsed = parseRewindNaturalSearch('meeting notes yesterday morning', NOW)
    const yesterdayMorning = new Date(2026, 6, 30, 6)
    expect(parsed).toEqual({
      query: 'meeting notes',
      from: yesterdayMorning.getTime(),
      to: yesterdayMorning.getTime() + 21_599_999
    })
  })

  it('removes temporal possessives from the normalized query', () => {
    expect(parseRewindNaturalSearch("today's meetings", NOW).query).toBe('meetings')
    expect(parseRewindNaturalSearch('yesterday’s invoice', NOW).query).toBe('invoice')
    expect(parseRewindNaturalSearch("this morning's meeting", NOW).query).toBe('meeting')
    expect(parseRewindNaturalSearch('this afternoon’s notes', NOW).query).toBe('notes')
  })

  it('keeps meaningful words that resemble question boilerplate', () => {
    expect(parseRewindNaturalSearch('The Daily Show yesterday', NOW).query).toBe('The Daily Show')
  })

  it('does not produce an inverted evening scope before evening starts', () => {
    const parsed = parseRewindNaturalSearch('this evening', NOW)
    expect(parsed.from).toBe(parsed.to)
  })

  it('clamps an active day part and prefers it over today', () => {
    const morning = new Date(2026, 6, 31, 9, 30)
    const parsed = parseRewindNaturalSearch('meeting this morning today', morning)
    const from = new Date(morning)
    from.setHours(6, 0, 0, 0)
    expect(parsed).toEqual({ query: 'meeting', from: from.getTime(), to: morning.getTime() })
  })

  it('does not produce an inverted morning scope before morning starts', () => {
    const parsed = parseRewindNaturalSearch('this morning', new Date(2026, 6, 31, 5, 30))
    expect(parsed.from).toBe(parsed.to)
  })

  it('leaves ordinary search unchanged', () => {
    expect(parseRewindNaturalSearch('quarterly review', NOW)).toEqual({
      query: 'quarterly review',
      from: null,
      to: null
    })
  })
})
