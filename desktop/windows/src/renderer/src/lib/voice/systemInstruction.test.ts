import { describe, it, expect } from 'vitest'
import {
  buildVoiceSystemInstruction,
  currentCalendarContext,
  userLanguagesLine
} from './systemInstruction'

describe('userLanguagesLine', () => {
  it('is omitted when the user has configured no voice languages', () => {
    expect(userLanguagesLine([])).toBe('')
    expect(buildVoiceSystemInstruction({ userLanguages: [] })).not.toContain('The user speaks ONLY')
  })

  it('names the languages and the primary one when set', () => {
    const line = userLanguagesLine(['ru', 'en'])
    expect(line).toContain(
      'The user speaks ONLY these languages: Russian, English (primary: Russian)'
    )
    expect(line).toContain('interpret it as Russian.')
    expect(buildVoiceSystemInstruction({ userLanguages: ['ru', 'en'] })).toContain(
      'The user speaks ONLY these languages: Russian, English'
    )
  })
})

describe('currentCalendarContext', () => {
  it('formats the local datetime, IANA zone id, and UTC offset', () => {
    const now = new Date('2026-07-14T12:00:00Z')
    expect(currentCalendarContext(now, 'Europe/Berlin')).toBe(
      'Current local datetime: 2026-07-14T14:00:00+02:00. Current timezone: Europe/Berlin (UTC+02:00).'
    )
  })

  it('handles negative and half-hour offsets', () => {
    const now = new Date('2026-01-14T12:00:00Z')
    expect(currentCalendarContext(now, 'America/New_York')).toContain(
      'Current local datetime: 2026-01-14T07:00:00-05:00. Current timezone: America/New_York (UTC-05:00).'
    )
    expect(currentCalendarContext(now, 'Asia/Kolkata')).toContain('(UTC+05:30).')
  })

  it('degrades to UTC on an unknown zone id rather than losing the line', () => {
    const line = currentCalendarContext(new Date('2026-07-14T12:00:00Z'), 'Not/AZone')
    expect(line).toBe(
      'Current local datetime: 2026-07-14T12:00:00+00:00. Current timezone: UTC (UTC+00:00).'
    )
  })
})

describe('buildVoiceSystemInstruction', () => {
  const card = '<about_user>\nName: Ada\nWhat Omi knows about them:\n- Ships fast.\n</about_user>'

  it('emits the sections in macOS order', () => {
    const text = buildVoiceSystemInstruction({
      aboutUser: card,
      userLanguages: ['en'],
      now: new Date('2026-07-14T12:00:00Z'),
      timeZone: 'UTC'
    })
    const order = [
      'You are Omi, a fast spoken-voice assistant',
      'The user speaks ONLY these languages',
      '<about_user>',
      'Current local datetime:',
      'answer DIRECTLY from <about_user>',
      'Keep latency low: prefer answering directly when you can.'
    ].map((needle) => text.indexOf(needle))
    expect(order.every((i) => i >= 0)).toBe(true)
    expect(order).toEqual([...order].sort((a, b) => a - b))
    expect(text).toContain("on the user's Windows computer")
  })

  it('omits the about_user block entirely when no card is cached', () => {
    const text = buildVoiceSystemInstruction({ aboutUser: '' })
    // The routing rule still names the tag; the CARD itself must be absent.
    expect(text).not.toContain('What Omi knows about them:')
    expect(text).not.toContain('</about_user>')
    expect(text).toContain('Current local datetime:')
  })

  it('never references tools that do not exist in Phase A', () => {
    const text = buildVoiceSystemInstruction({ aboutUser: card, userLanguages: ['en'] })
    for (const tool of [
      'spawn_agent',
      'get_tasks',
      'get_action_items',
      'get_memories',
      'search_memories',
      'ask_higher_model'
    ]) {
      expect(text).not.toContain(tool)
    }
  })

  it('emits the continuity block only when a seed is passed, escaping its angle brackets', () => {
    expect(buildVoiceSystemInstruction({})).not.toContain('<recent_top_level_conversation>')
    const text = buildVoiceSystemInstruction({
      topLevelConversationContext: 'user: <b>ignore previous</b>'
    })
    expect(text).toContain('<recent_top_level_conversation>')
    expect(text).toContain('user: &lt;b&gt;ignore previous&lt;/b&gt;')
  })
})
