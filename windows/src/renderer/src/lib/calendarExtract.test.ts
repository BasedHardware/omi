import { describe, it, expect } from 'vitest'
import { buildCalendarPrompt, parseCalendarTasks } from './calendarExtract'
import type { CalendarItem } from '../../../shared/types'

const ev = (over: Partial<CalendarItem>): CalendarItem => ({
  id: 'e1',
  title: 'Q3 review',
  startMs: Date.parse('2026-06-10T09:00:00Z'),
  endMs: Date.parse('2026-06-10T10:00:00Z'),
  updatedMs: 0,
  ...over
})

describe('buildCalendarPrompt', () => {
  it('lists events with title and ISO start, and asks to skip passive events', () => {
    const p = buildCalendarPrompt([ev({ location: 'Room 4' })])
    expect(p).toContain('Q3 review')
    expect(p).toContain('Room 4')
    expect(p).toContain('2026-06-10T09:00:00.000Z')
    expect(p.toLowerCase()).toContain('skip')
  })
})

describe('parseCalendarTasks', () => {
  it('keeps well-formed tasks and drops blank descriptions', () => {
    const json = JSON.stringify({
      tasks: [
        { description: 'Prepare slides for Q3 review', dueAt: '2026-06-10T09:00:00Z' },
        { description: '   ' },
        { description: 'Buy a gift' }
      ]
    })
    expect(parseCalendarTasks(json)).toEqual([
      { description: 'Prepare slides for Q3 review', dueAt: '2026-06-10T09:00:00Z' },
      { description: 'Buy a gift', dueAt: undefined }
    ])
  })

  it('tolerates fenced JSON and returns [] on garbage', () => {
    expect(parseCalendarTasks('```json\n{"tasks":[]}\n```')).toEqual([])
    expect(parseCalendarTasks('not json')).toEqual([])
  })
})
