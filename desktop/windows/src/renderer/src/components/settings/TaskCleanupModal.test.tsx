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
  expires_in_seconds: 300,
  total_open_action_items: 2,
  scan_cap: 2000,
  scan_truncated: false
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

// Scan-cap truncation: get_action_items caps at 2000 open tasks, so accounts
// with more than that get a silently partial scan unless the UI says so.
describe('TaskCleanupModal scan truncation notice', () => {
  it('shows a truncation notice when scan_truncated is true', async () => {
    vi.mocked(taskCleanupPreview).mockResolvedValue({
      ...PREVIEW_RESULT,
      total_open_action_items: 45000,
      scan_cap: 2000,
      scan_truncated: true
    })

    render(<TaskCleanupModal open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('Analyze'))

    await screen.findByText(/2,000 oldest open tasks/)
    expect(screen.getByText(/43,000 weren't checked/)).toBeTruthy()
  })

  it('shows no truncation notice when scan_truncated is false', async () => {
    render(<TaskCleanupModal open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('Analyze'))

    await screen.findByText('Renew passport')
    expect(screen.queryByText(/weren't checked/)).toBeNull()
  })
})
