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

  it('keeps combined relative dates and day parts in one scope', () => {
    const parsed = parseRewindNaturalSearch('meeting notes yesterday morning', NOW)
    const yesterdayMorning = new Date(2026, 6, 30, 6)
    expect(parsed).toEqual({
      query: 'meeting notes',
      from: yesterdayMorning.getTime(),
      to: yesterdayMorning.getTime() + 21_599_999
    })
  })

  it('does not produce an inverted evening scope before evening starts', () => {
    const parsed = parseRewindNaturalSearch('this evening', NOW)
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
