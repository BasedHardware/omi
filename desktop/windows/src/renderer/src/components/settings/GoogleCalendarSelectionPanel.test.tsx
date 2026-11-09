// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { GoogleCalendarSelectionPanel } from './GoogleCalendarSelectionPanel'

const h = vi.hoisted(() => ({
  auth: { currentUser: { uid: 'owner' } as { uid: string } | null },
  changed: undefined as undefined | (() => void),
  load: vi.fn(),
  save: vi.fn()
}))
vi.mock('../../lib/firebase', () => ({ auth: h.auth }))
vi.mock('firebase/auth', () => ({
  onAuthStateChanged: (_auth: unknown, callback: () => void) => {
    h.changed = callback
    return () => {
      h.changed = undefined
    }
  }
}))
vi.mock('../../lib/googleCalendarSelection', () => ({
  loadGoogleCalendarSelection: h.load,
  saveGoogleCalendarSelection: h.save
}))
const catalog = () => ({
  account_id: 'personal@example.test',
  owner: h.auth.currentUser,
  calendars: [
    { id: 'personal', name: 'Personal', primary: true, available: true },
    { id: 'team', name: 'Team', primary: false, available: true },
    { id: 'removed', name: '', primary: false, available: false }
  ],
  selected_ids: ['personal'],
  write_calendar_id: 'primary'
})
beforeEach(() => {
  h.auth.currentUser = { uid: 'owner' }
  h.load.mockReset().mockImplementation(async () => catalog())
  h.save
    .mockReset()
    .mockImplementation(async (_data, selected_ids) => ({ ...catalog(), selected_ids }))
})
afterEach(cleanup)
async function open(): Promise<void> {
  render(<GoogleCalendarSelectionPanel />)
  fireEvent.click(screen.getByRole('button', { name: 'Choose Calendars' }))
  await screen.findByLabelText('Personal')
}

it('only Save persists a local selection, Cancel restores it and primary can be excluded', async () => {
  await open()
  expect(screen.getByText('Read selected calendars. New events use Personal.')).toBeTruthy()
  fireEvent.click(screen.getByLabelText('Team'))
  expect(h.save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect((screen.getByLabelText('Team') as HTMLInputElement).checked).toBe(false)
  fireEvent.click(screen.getByLabelText('Personal'))
  expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByLabelText('Team'))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(h.save).toHaveBeenCalledWith(expect.anything(), ['team']))
  expect((screen.getByLabelText('Personal') as HTMLInputElement).checked).toBe(false)
})

it('saved unavailable calendars can be removed without selecting them again', async () => {
  h.load.mockResolvedValue({ ...catalog(), selected_ids: ['personal', 'removed'] })
  await open()
  const removed = screen.getByLabelText('removed — No longer available') as HTMLInputElement
  expect(removed.checked).toBe(true)
  fireEvent.click(removed)
  expect(removed.disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(h.save).toHaveBeenCalledWith(expect.anything(), ['personal']))
})

it('a failed save keeps the draft and can retry without losing the choice', async () => {
  h.save.mockRejectedValueOnce(new Error('unavailable'))
  await open()
  fireEvent.click(screen.getByLabelText('Team'))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await screen.findByRole('alert')
  expect((screen.getByLabelText('Team') as HTMLInputElement).checked).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(h.save).toHaveBeenCalledTimes(2))
})

it('an account replacement clears the displayed calendar names and draft', async () => {
  await open()
  act(() => {
    h.auth.currentUser = { uid: 'replacement' }
    h.changed!()
  })
  expect(screen.queryByLabelText('Personal')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  expect(h.save).not.toHaveBeenCalled()
})

it('an old load completing after an account replacement cannot publish names', async () => {
  let release!: (value: ReturnType<typeof catalog>) => void
  const old = catalog()
  h.load.mockReturnValue(
    new Promise((resolve) => {
      release = resolve
    })
  )
  render(<GoogleCalendarSelectionPanel />)
  fireEvent.click(screen.getByRole('button', { name: 'Choose Calendars' }))
  act(() => {
    h.auth.currentUser = { uid: 'replacement' }
    h.changed!()
  })
  await act(async () => {
    release(old)
  })
  expect(screen.queryByLabelText('Personal')).toBeNull()
})
