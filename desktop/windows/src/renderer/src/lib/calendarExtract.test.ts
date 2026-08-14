import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { CalendarItem } from '../../../shared/types'

const { omiPost } = vi.hoisted(() => ({ omiPost: vi.fn() }))
vi.mock('./apiClient', () => ({
  omiApi: { post: omiPost }
}))

import { formatCalendarItems, extractCalendarTasks } from './calendarExtract'

const ev = (over: Partial<CalendarItem>): CalendarItem => ({
  id: 'e1',
  title: 'Q3 review',
  startMs: Date.parse('2026-06-10T09:00:00Z'),
  endMs: Date.parse('2026-06-10T10:00:00Z'),
  updatedMs: 0,
  ...over
})

beforeEach(() => {
  omiPost.mockReset()
})

describe('formatCalendarItems', () => {
  it('renders title, location and ISO start per event', () => {
    expect(formatCalendarItems([ev({ location: 'Room 4' })])).toEqual([
      'Q3 review @ Room 4 | starts 2026-06-10T09:00:00.000Z | id=e1'
    ])
  })
})

describe('extractCalendarTasks', () => {
  it('sends the calendar source to the backend synthesis SSOT and maps returned tasks', async () => {
    omiPost.mockResolvedValue({
      data: {
        memories: [],
        tasks: [
          {
            description: 'Prepare slides for Q3 review',
            priority: 'high',
            due_at: '2026-06-10T09:00:00Z'
          },
          { description: '   ' },
          { description: 'Buy a gift', priority: 'low' }
        ],
        profile: ''
      }
    })

    const tasks = await extractCalendarTasks([ev({})])

    expect(omiPost).toHaveBeenCalledWith(
      '/v1/connectors/synthesize',
      expect.objectContaining({ source: 'calendar' }),
      expect.anything()
    )
    expect(tasks).toEqual([
      { description: 'Prepare slides for Q3 review', dueAt: '2026-06-10T09:00:00Z' },
      { description: 'Buy a gift', dueAt: undefined }
    ])
  })

  it('never calls the backend for an empty event list', async () => {
    expect(await extractCalendarTasks([])).toEqual([])
    expect(omiPost).not.toHaveBeenCalled()
  })
})
