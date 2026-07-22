// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { InsightRecord } from '../../../shared/types'

// The Insights history page reads window.omi.insightRecent(100) and drives
// dismiss / mark-all-read / clear over additive IPC. These tests mock that IPC
// surface and assert: the list renders, per-item dismiss calls the IPC, mark-all
// flips every row, and the empty state shows when there is no history.

const insightRecent = vi.fn()
const insightDismissRecord = vi.fn()
const insightDismissAll = vi.fn()
const insightClearAll = vi.fn()

vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

const rec = (over: Partial<InsightRecord> & { id: number; headline: string }): InsightRecord => ({
  ts: Date.now(),
  advice: 'some advice',
  reasoning: 'some reasoning',
  category: 'productivity',
  sourceApp: 'Slack',
  confidence: 0.8,
  dismissed: 0,
  ...over
})

beforeEach(() => {
  insightRecent.mockReset()
  insightDismissRecord.mockReset().mockResolvedValue(true)
  insightDismissAll.mockReset().mockResolvedValue(0)
  insightClearAll.mockReset().mockResolvedValue(0)
  ;(window as unknown as { omi: unknown }).omi = {
    insightRecent,
    insightDismissRecord,
    insightDismissAll,
    insightClearAll
  }
})

afterEach(() => {
  cleanup()
  vi.resetModules()
})

async function renderInsights(): Promise<void> {
  const { Insights } = await import('./Insights')
  render(
    <MemoryRouter>
      <Insights />
    </MemoryRouter>
  )
}

describe('Insights page', () => {
  it('renders records from insightRecent, newest-first as returned', async () => {
    insightRecent.mockResolvedValue([
      rec({ id: 2, headline: 'Newer insight', advice: 'do X' }),
      rec({ id: 1, headline: 'Older insight', advice: 'do Y' })
    ])
    await renderInsights()

    await waitFor(() => expect(screen.queryByText('Newer insight')).not.toBeNull())
    expect(screen.queryByText('Older insight')).not.toBeNull()
    expect(insightRecent).toHaveBeenCalledWith(100)
    // Header count reflects the two records.
    expect(screen.queryByText(/2 total/)).not.toBeNull()
  })

  it('expanding a row then Dismiss calls insightDismissRecord with the id', async () => {
    insightRecent.mockResolvedValue([rec({ id: 42, headline: 'Take a break' })])
    await renderInsights()

    await waitFor(() => expect(screen.queryByText('Take a break')).not.toBeNull())
    // The row is a button (inline expand); click it to reveal the detail + Dismiss.
    fireEvent.click(screen.getByText('Take a break'))
    const dismissBtn = await screen.findByRole('button', { name: /^Dismiss$/ })
    fireEvent.click(dismissBtn)

    await waitFor(() => expect(insightDismissRecord).toHaveBeenCalledWith(42))
  })

  it('Mark all read flips every unread row and calls insightDismissAll', async () => {
    insightRecent.mockResolvedValue([
      rec({ id: 1, headline: 'One' }),
      rec({ id: 2, headline: 'Two' })
    ])
    await renderInsights()

    await waitFor(() => expect(screen.queryByText('One')).not.toBeNull())
    // Two unread → the subtitle shows the unread count.
    expect(screen.queryByText(/2 unread/)).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Mark all read/i }))
    await waitFor(() => expect(insightDismissAll).toHaveBeenCalled())
    // Optimistic flip clears the unread count from the subtitle.
    await waitFor(() => expect(screen.queryByText(/unread/)).toBeNull())
  })

  it('shows the empty state when there is no history', async () => {
    insightRecent.mockResolvedValue([])
    await renderInsights()

    await waitFor(() => expect(screen.queryByText('No insights yet')).not.toBeNull())
  })

  it('search filters the visible list by headline/advice/source', async () => {
    insightRecent.mockResolvedValue([
      rec({ id: 1, headline: 'Reply to Sarah', advice: 'in Slack', sourceApp: 'Slack' }),
      rec({ id: 2, headline: 'Stretch break', advice: 'stand up', sourceApp: 'System' })
    ])
    await renderInsights()

    await waitFor(() => expect(screen.queryByText('Reply to Sarah')).not.toBeNull())
    fireEvent.change(screen.getByPlaceholderText('Search insights…'), {
      target: { value: 'stretch' }
    })
    expect(screen.queryByText('Stretch break')).not.toBeNull()
    expect(screen.queryByText('Reply to Sarah')).toBeNull()
  })
})
