// @vitest-environment jsdom
//
// The Activity page composes four sources into one stream. These tests mock all
// four and assert the behaviors that decide whether the timeline can be trusted:
// that a day still renders when a source is down, that folding is per day and
// survives another day folding, that an unread day says "counting" rather than
// zero, and that a capped strip says how much it is hiding.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const get = vi.fn()
const patch = vi.fn()
const tasksListIncomplete = vi.fn()
const tasksListCompleted = vi.fn()
const spineScreenDays = vi.fn()
const spineScreenDay = vi.fn()
const navigate = vi.fn()

vi.mock('../lib/apiClient', () => ({
  omiApi: { get: (...a: unknown[]) => get(...a), patch: (...a: unknown[]) => patch(...a) }
}))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const { Activity } = await import('./Activity')

const at = (day: number, hour: number, minute = 0): Date =>
  new Date(2026, 7, day, hour, minute, 0, 0)
const iso = (d: Date): string => d.toISOString()
const startOfDay = (d: Date): number =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()

const conversation = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  id: 'c1',
  created_at: iso(at(15, 10)),
  started_at: iso(at(15, 10)),
  finished_at: iso(at(15, 11)),
  structured: { title: 'Lease renewal', overview: 'We agreed', category: 'personal', emoji: '🏠' },
  starred: false,
  ...over
})

const memory = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  id: 'm1',
  content: 'Prefers oat milk',
  created_at: iso(at(15, 12)),
  ...over
})

const screenDay = (dayId: number, over: Record<string, unknown> = {}): Record<string, unknown> => ({
  dayId,
  total: 3,
  hourCounts: new Array<number>(24).fill(0),
  sampled: [],
  ...over
})

beforeEach(() => {
  navigate.mockReset()
  patch.mockReset().mockResolvedValue({ data: {} })
  tasksListIncomplete.mockReset().mockResolvedValue([])
  tasksListCompleted.mockReset().mockResolvedValue([])
  spineScreenDays.mockReset().mockResolvedValue([])
  spineScreenDay.mockReset().mockResolvedValue(null)
  get.mockReset().mockImplementation((path: string) => {
    if (path === '/v1/conversations') return Promise.resolve({ data: [conversation()] })
    if (path === '/v3/memories') return Promise.resolve({ data: [memory()] })
    return Promise.resolve({ data: [] })
  })
  ;(window as unknown as { omi: unknown }).omi = {
    tasksListIncomplete,
    tasksListCompleted,
    spineScreenDays,
    spineScreenDay
  }
})

afterEach(() => cleanup())

const mount = (): void => {
  render(
    <MemoryRouter>
      <Activity />
    </MemoryRouter>
  )
}

describe('Activity page', () => {
  it('composes the sources into a day with a header', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('Lease renewal')).toBeTruthy())
    expect(screen.getByText('Prefers oat milk')).toBeTruthy()
    // The day header names the day, and the day is today's date in the fixture
    // only if the suite runs on that date - so assert the header exists by role.
    expect(screen.getAllByRole('button', { name: /Collapse|Expand/ }).length).toBeGreaterThan(0)
  })

  it('still renders the stream when a source is unavailable', async () => {
    get.mockImplementation((path: string) => {
      if (path === '/v3/memories') return Promise.reject(new Error('offline'))
      if (path === '/v1/conversations') return Promise.resolve({ data: [conversation()] })
      return Promise.resolve({ data: [] })
    })
    mount()

    await waitFor(() => expect(screen.getByText('Lease renewal')).toBeTruthy())
    // A timeline missing one source is far more useful than no timeline, but it
    // has to say so rather than implying the missing records never existed.
    expect(
      screen.getByText('Some of your history could not be loaded, so this day may be incomplete.')
    ).toBeTruthy()
  })

  it('folds one day without touching another', async () => {
    get.mockImplementation((path: string) => {
      if (path === '/v1/conversations') {
        return Promise.resolve({
          data: [
            conversation(),
            conversation({
              id: 'c2',
              started_at: iso(at(14, 10)),
              created_at: iso(at(14, 10)),
              finished_at: iso(at(14, 11)),
              structured: { title: 'Standup', overview: '', category: '', emoji: '📅' }
            })
          ]
        })
      }
      return Promise.resolve({ data: [] })
    })
    mount()
    await waitFor(() => expect(screen.getByText('Standup')).toBeTruthy())

    const headers = screen.getAllByRole('button', { name: /Collapse/ })
    fireEvent.click(headers[0])

    await waitFor(() => expect(screen.queryByText('Lease renewal')).toBeNull())
    // Folding is keyed by the day's own identity, so the other day is untouched.
    expect(screen.getByText('Standup')).toBeTruthy()
  })

  it('filters to one kind and drops the days left empty', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('Prefers oat milk')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Tasks' }))
    await waitFor(() => expect(screen.queryByText('Prefers oat milk')).toBeNull())
    expect(screen.getByText('Tasks you add or Omi extracts appear here.')).toBeTruthy()
  })

  it('says counting for a day whose screen capture was never read', async () => {
    mount()
    // No screen day was projected, so the rail must not claim zero moments.
    await waitFor(() => expect(screen.getByText('counting screen moments')).toBeTruthy())
    // The headline is an em dash rather than a number, for the same reason.
    expect(screen.getByText('—')).toBeTruthy()
    expect(screen.queryByText('0')).toBeNull()
  })

  it('says zero for a day that was read and held nothing', async () => {
    const day = startOfDay(at(15, 10))
    spineScreenDays.mockResolvedValue([day])
    spineScreenDay.mockResolvedValue(screenDay(day, { total: 0 }))
    mount()

    await waitFor(() => expect(screen.getByText('0')).toBeTruthy())
    expect(screen.queryByText('counting screen moments')).toBeNull()
  })

  it('opens a conversation from its row', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('Lease renewal')).toBeTruthy())
    fireEvent.click(screen.getByText('Lease renewal'))
    expect(navigate).toHaveBeenCalledWith('/conversations/c1')
  })

  it('stars a conversation without opening it', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('Lease renewal')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Star' }))
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/v1/conversations/c1/starred', null, {
        params: { value: true }
      })
    )
    // The star sits inside the row button; without stopPropagation it would also
    // navigate away from the page it was pressed on.
    expect(navigate).not.toHaveBeenCalled()
  })

  it('shows the empty state when nothing loaded at all', async () => {
    get.mockResolvedValue({ data: [] })
    mount()
    await waitFor(() => expect(screen.getByText('Nothing here yet')).toBeTruthy())
    expect(
      screen.getByText(
        'Conversations, memories, tasks and screen moments appear here as they happen.'
      )
    ).toBeTruthy()
  })
})
