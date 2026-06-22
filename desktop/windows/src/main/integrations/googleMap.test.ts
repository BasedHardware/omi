import { describe, it, expect } from 'vitest'
import { mapGmailMessage, mapCalendarEvent } from './googleMap'

describe('mapGmailMessage', () => {
  it('extracts Subject/From headers, snippet, and numeric internalDate', () => {
    const item = mapGmailMessage({
      id: 'm1',
      snippet: 'Your order shipped',
      internalDate: '1700000000000',
      payload: {
        headers: [
          { name: 'From', value: 'Shop <shop@example.com>' },
          { name: 'Subject', value: 'Order #42' }
        ]
      }
    })
    expect(item).toEqual({
      id: 'm1',
      subject: 'Order #42',
      from: 'Shop <shop@example.com>',
      snippet: 'Your order shipped',
      internalDateMs: 1700000000000
    })
  })

  it('header lookup is case-insensitive and tolerates missing fields', () => {
    const item = mapGmailMessage({ id: 'm2', payload: { headers: [{ name: 'subject', value: 'Hi' }] } })
    expect(item).toEqual({ id: 'm2', subject: 'Hi', from: '', snippet: '', internalDateMs: 0 })
  })

  it('returns null without an id', () => {
    expect(mapGmailMessage({ snippet: 'x' })).toBeNull()
  })
})

describe('mapCalendarEvent', () => {
  it('maps a timed event', () => {
    const item = mapCalendarEvent({
      id: 'e1',
      summary: 'Dentist',
      location: 'Clinic',
      updated: '2026-06-01T10:00:00Z',
      start: { dateTime: '2026-06-10T09:00:00Z' },
      end: { dateTime: '2026-06-10T09:30:00Z' }
    })
    expect(item?.id).toBe('e1')
    expect(item?.title).toBe('Dentist')
    expect(item?.location).toBe('Clinic')
    expect(item?.startMs).toBe(Date.parse('2026-06-10T09:00:00Z'))
    expect(item?.endMs).toBe(Date.parse('2026-06-10T09:30:00Z'))
  })

  it('handles all-day events (date, not dateTime) and missing summary', () => {
    const item = mapCalendarEvent({ id: 'e2', start: { date: '2026-06-10' }, end: { date: '2026-06-11' } })
    expect(item?.title).toBe('(no title)')
    expect(item?.startMs).toBe(Date.parse('2026-06-10'))
    expect(item?.location).toBeUndefined()
  })

  it('returns null without an id', () => {
    expect(mapCalendarEvent({ summary: 'x' })).toBeNull()
  })
})
