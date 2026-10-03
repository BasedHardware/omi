// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, within } from '@testing-library/react'
import type { ConversationAnalytics, TranscriptSegment } from '../../lib/omiApi.generated'
import { ConversationAnalyticsPanel } from './ConversationAnalyticsPanel'

const getMock = vi.fn()
vi.mock('../../lib/apiClient', () => ({
  omiApi: { get: (...args: unknown[]) => getMock(...args) }
}))

const SEGMENTS: TranscriptSegment[] = []
const ANALYTICS: ConversationAnalytics = {
  conversation_id: 'conv1',
  total_seconds: 150,
  total_words: 333,
  words_per_minute: 133.2,
  speaker_count: 3,
  speakers: [
    {
      speaker: 'You',
      is_user: true,
      talk_seconds: 90,
      word_count: 180,
      words_per_minute: 120,
      talk_share: 0.6
    },
    {
      speaker: 'Unknown',
      person_id: 'p1',
      talk_seconds: 60,
      word_count: 150,
      words_per_minute: 150,
      talk_share: 0.4
    },
    {
      speaker: 'Unknown',
      person_id: 'p2',
      talk_seconds: 0,
      word_count: 3,
      words_per_minute: 0,
      talk_share: 0
    }
  ]
}

beforeEach(() => {
  getMock.mockReset()
  getMock.mockResolvedValue({ data: ANALYTICS })
})
afterEach(cleanup)

describe('ConversationAnalyticsPanel', () => {
  it('loads on demand and preserves the server metrics, order, duplicate labels, and zero-duration rows', async () => {
    const view = render(
      <ConversationAnalyticsPanel conversationId="conv1" transcriptSegments={SEGMENTS} />
    )
    expect(getMock).not.toHaveBeenCalled()
    fireEvent.click(view.getByRole('button', { name: 'Speaker analytics' }))
    expect(view.getByRole('status').textContent).toContain('Loading speaker analytics')

    const table = await view.findByRole('table')
    expect(getMock).toHaveBeenCalledWith('/v1/conversations/conv1/analytics', {
      signal: expect.any(AbortSignal)
    })
    // Even an empty local transcript must display the authoritative API result.
    expect(
      within(table)
        .getAllByRole('rowheader')
        .map((row) => row.textContent)
    ).toEqual(['You', 'Unknown', 'Unknown'])
    const rows = within(table).getAllByRole('row').slice(1)
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole('cell')
          .map((cell) => cell.textContent)
      )
    ).toEqual([
      ['1m 30s', '60%', '120'],
      ['1m 0s', '40%', '150'],
      ['0s', '0%', '0']
    ])
    expect(view.getByText('2m 30s')).toBeTruthy()
    expect(view.getByText('333')).toBeTruthy()
  })

  it('shows a friendly failure and retries without exposing the response error', async () => {
    getMock.mockRejectedValueOnce(new Error('private backend response'))
    const view = render(
      <ConversationAnalyticsPanel conversationId="conv1" transcriptSegments={SEGMENTS} />
    )
    fireEvent.click(view.getByRole('button', { name: 'Speaker analytics' }))
    expect((await view.findByRole('alert')).textContent).toBe('Couldn’t load speaker analytics.')
    expect(view.queryByText('private backend response')).toBeNull()
    fireEvent.click(view.getByRole('button', { name: 'Try again' }))
    await view.findByRole('table')
    expect(getMock).toHaveBeenCalledTimes(2)
    expect(view.queryByRole('alert')).toBeNull()
  })

  it('shows an empty result instead of a table of invented zero metrics', async () => {
    getMock.mockResolvedValue({
      data: {
        ...ANALYTICS,
        speakers: [],
        speaker_count: 0,
        total_seconds: 0,
        total_words: 0,
        words_per_minute: 0
      }
    })
    const view = render(
      <ConversationAnalyticsPanel conversationId="conv1" transcriptSegments={SEGMENTS} />
    )
    fireEvent.click(view.getByRole('button', { name: 'Speaker analytics' }))
    await view.findByText('No speaker analytics available for this conversation.')
    expect(view.queryByRole('table')).toBeNull()
  })

  it('aborts on collapse and ignores a late response after the panel is reopened', async () => {
    let finishOld!: (result: { data: ConversationAnalytics }) => void
    getMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve
        })
    )
    const view = render(
      <ConversationAnalyticsPanel conversationId="conv1" transcriptSegments={SEGMENTS} />
    )
    const toggle = view.getByRole('button', { name: 'Speaker analytics' })
    fireEvent.click(toggle)
    const oldSignal = getMock.mock.calls[0][1].signal as AbortSignal
    fireEvent.click(toggle)
    expect(oldSignal.aborted).toBe(true)
    fireEvent.click(toggle)
    await view.findByRole('table')
    await act(async () => finishOld({ data: { ...ANALYTICS, total_words: 999 } }))
    expect(view.queryByText('999')).toBeNull()
    expect(view.getByText('333')).toBeTruthy()
    const currentSignal = getMock.mock.calls[1][1].signal as AbortSignal
    view.unmount()
    expect(currentSignal.aborted).toBe(true)
  })

  it('refreshes server grouping after the transcript is updated by speaker naming', async () => {
    const view = render(
      <ConversationAnalyticsPanel conversationId="conv1" transcriptSegments={SEGMENTS} />
    )
    fireEvent.click(view.getByRole('button', { name: 'Speaker analytics' }))
    await view.findByRole('table')
    getMock.mockResolvedValue({
      data: { ...ANALYTICS, speakers: [{ ...ANALYTICS.speakers![0], speaker: 'Sam' }] }
    })
    view.rerender(
      <ConversationAnalyticsPanel conversationId="conv1" transcriptSegments={[...SEGMENTS]} />
    )
    await view.findByRole('rowheader', { name: 'Sam' })
    expect(view.queryByRole('rowheader', { name: 'You' })).toBeNull()
    expect(getMock).toHaveBeenCalledTimes(2)
  })
})
