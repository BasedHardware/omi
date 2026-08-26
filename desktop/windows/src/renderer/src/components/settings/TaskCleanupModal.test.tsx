// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { TaskCleanupModal } from './TaskCleanupModal'
import { taskCleanupPreview, taskCleanupExecute } from '../../lib/taskCleanup'

vi.mock('../../lib/taskCleanup', async () => {
  const actual =
    await vi.importActual<typeof import('../../lib/taskCleanup')>('../../lib/taskCleanup')
  return { ...actual, taskCleanupPreview: vi.fn(), taskCleanupExecute: vi.fn() }
})

const tasksReconcile = vi.fn()

const PREVIEW_RESULT = {
  session_id: 'sess-1',
  total_candidates: 2,
  breakdown: { stale_age: 2 },
  sample: [],
  candidate_ids: ['t1', 't2'],
  candidate_meta: [
    { id: 't1', strategy: 'stale_age', description: 'Renew passport' },
    { id: 't2', strategy: 'stale_age', description: 'Book dentist' }
  ],
  expires_in_seconds: 300
}

beforeEach(() => {
  vi.mocked(taskCleanupPreview).mockReset().mockResolvedValue(PREVIEW_RESULT)
  vi.mocked(taskCleanupExecute).mockReset().mockResolvedValue({ deleted_count: 1 })
  tasksReconcile.mockReset().mockResolvedValue(undefined)
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = { tasksReconcile }
})

afterEach(() => cleanup())

// Per-item exclusion: the preview shows every candidate (not just a capped
// sample), unchecking one keeps it out of the delete count and out of the
// execute call's excluded_ids.
describe('TaskCleanupModal review list', () => {
  it('unchecking a candidate excludes it from the delete count and the execute call', async () => {
    render(<TaskCleanupModal open onOpenChange={vi.fn()} />)

    fireEvent.click(screen.getByText('Analyze'))

    await screen.findByText('Renew passport')
    expect(screen.getByText('Book dentist')).toBeTruthy()
    expect(screen.getByText('Delete 2 tasks')).toBeTruthy()

    const [passportCheckbox] = screen
      .getAllByRole('checkbox')
      .filter((cb) => cb.closest('li')?.textContent?.includes('Renew passport'))
    fireEvent.click(passportCheckbox)

    expect(screen.getByText('Delete 1 task')).toBeTruthy()

    fireEvent.click(screen.getByText('Delete 1 task'))

    await waitFor(() => expect(taskCleanupExecute).toHaveBeenCalledWith('sess-1', ['t1']))
  })

  it('deselecting every candidate disables the delete button', async () => {
    render(<TaskCleanupModal open onOpenChange={vi.fn()} />)

    fireEvent.click(screen.getByText('Analyze'))
    await screen.findByText('Renew passport')

    fireEvent.click(screen.getByText('Deselect all'))

    const deleteButton = screen.getByText('Delete 0 tasks').closest('button') as HTMLButtonElement
    expect(deleteButton.disabled).toBe(true)
    expect(taskCleanupExecute).not.toHaveBeenCalled()
  })
})
