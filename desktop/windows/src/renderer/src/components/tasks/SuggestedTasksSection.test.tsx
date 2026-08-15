// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import type { SuggestedCandidate } from '../../lib/suggestedTasks'

const loadMock = vi.fn()
const acceptMock = vi.fn()
const rejectMock = vi.fn()
vi.mock('../../lib/suggestedTasks', () => ({
  loadSuggestedCandidates: (...a: unknown[]) => loadMock(...a),
  acceptSuggestedCandidate: (...a: unknown[]) => acceptMock(...a),
  rejectSuggestedCandidate: (...a: unknown[]) => rejectMock(...a)
}))

import { SuggestedTasksSection } from './SuggestedTasksSection'

const card = (over: Partial<SuggestedCandidate> = {}): SuggestedCandidate => ({
  id: 'c-1',
  title: 'Reply to the vendor thread',
  detail: 'seen in Slack',
  accountGeneration: 1,
  ...over
})

beforeEach(() => {
  window.localStorage.clear()
  loadMock.mockReset()
  acceptMock.mockReset()
  rejectMock.mockReset()
})

afterEach(() => {
  cleanup()
})

describe('SuggestedTasksSection', () => {
  it('renders nothing while empty and shows the collapsed rail once loaded', async () => {
    loadMock.mockResolvedValue({ candidates: [card()], accountGeneration: 1 })
    render(<SuggestedTasksSection onAccepted={() => {}} />)
    await waitFor(() => expect(screen.queryByTestId('suggested-section')).not.toBeNull())
    // Collapsed by default (mac's AppStorage default false): count visible, cards not.
    expect(screen.getByTestId('suggested-toggle').textContent).toContain('1')
    expect(screen.queryByText('Reply to the vendor thread')).toBeNull()
  })

  it('expands to show cards and persists the expansion', async () => {
    loadMock.mockResolvedValue({ candidates: [card()], accountGeneration: 1 })
    render(<SuggestedTasksSection onAccepted={() => {}} />)
    await waitFor(() => expect(screen.queryByTestId('suggested-toggle')).not.toBeNull())
    fireEvent.click(screen.getByTestId('suggested-toggle'))
    expect(screen.getByText('Reply to the vendor thread')).not.toBeNull()
    expect(screen.getByText('seen in Slack')).not.toBeNull()
    expect(window.localStorage.getItem('omi.suggestedExpanded.v1')).toBe('true')
  })

  it('renders nothing at all when the rail is empty', async () => {
    loadMock.mockResolvedValue({ candidates: [], accountGeneration: 1 })
    render(<SuggestedTasksSection onAccepted={() => {}} />)
    await waitFor(() => expect(loadMock).toHaveBeenCalled())
    expect(screen.queryByTestId('suggested-section')).toBeNull()
  })

  it('accept removes the card optimistically and notifies the page', async () => {
    loadMock.mockResolvedValue({ candidates: [card()], accountGeneration: 1 })
    acceptMock.mockResolvedValue({ taskId: 't-1' })
    const onAccepted = vi.fn()
    render(<SuggestedTasksSection onAccepted={onAccepted} />)
    await waitFor(() => expect(screen.queryByTestId('suggested-toggle')).not.toBeNull())
    fireEvent.click(screen.getByTestId('suggested-toggle'))

    fireEvent.click(screen.getByTestId('suggested-accept-c-1'))
    expect(screen.queryByText('Reply to the vendor thread')).toBeNull()
    await waitFor(() => expect(onAccepted).toHaveBeenCalled())
    expect(acceptMock).toHaveBeenCalledWith(expect.objectContaining({ id: 'c-1' }))
  })

  it('restores the card with the sync-error copy when accept fails', async () => {
    loadMock.mockResolvedValue({ candidates: [card()], accountGeneration: 1 })
    acceptMock.mockRejectedValue(new Error('down'))
    render(<SuggestedTasksSection onAccepted={() => {}} />)
    await waitFor(() => expect(screen.queryByTestId('suggested-toggle')).not.toBeNull())
    fireEvent.click(screen.getByTestId('suggested-toggle'))

    fireEvent.click(screen.getByTestId('suggested-accept-c-1'))
    await waitFor(() => expect(screen.queryByText('Reply to the vendor thread')).not.toBeNull())
    expect(screen.getByTestId('suggested-error').textContent).toBe(
      'That Suggested action did not sync. Try again.'
    )
  })

  it('reject removes the card without notifying the page', async () => {
    loadMock.mockResolvedValue({ candidates: [card()], accountGeneration: 1 })
    rejectMock.mockResolvedValue(undefined)
    const onAccepted = vi.fn()
    render(<SuggestedTasksSection onAccepted={onAccepted} />)
    await waitFor(() => expect(screen.queryByTestId('suggested-toggle')).not.toBeNull())
    fireEvent.click(screen.getByTestId('suggested-toggle'))

    fireEvent.click(screen.getByTestId('suggested-reject-c-1'))
    await waitFor(() => expect(rejectMock).toHaveBeenCalled())
    expect(screen.queryByText('Reply to the vendor thread')).toBeNull()
    expect(onAccepted).not.toHaveBeenCalled()
  })

  it('shows the load-failure copy when the rail cannot refresh', async () => {
    loadMock.mockRejectedValue(new Error('offline'))
    render(<SuggestedTasksSection onAccepted={() => {}} />)
    await waitFor(() => expect(screen.queryByTestId('suggested-error')).not.toBeNull())
    expect(screen.getByTestId('suggested-error').textContent).toBe(
      'Suggested items could not be refreshed.'
    )
  })
})
