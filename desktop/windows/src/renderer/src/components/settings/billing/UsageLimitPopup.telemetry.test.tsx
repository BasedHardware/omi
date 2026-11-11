// @vitest-environment jsdom
import { render, cleanup, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi, afterEach } from 'vitest'
const sink = vi.hoisted(() => vi.fn())
vi.mock('../../../lib/analytics', () => ({ trackPurchaseEvent: sink, trackPaywallOpened: vi.fn() }))
vi.mock('../../../lib/byokKeys', () => ({ hasTranscriptionByokCached: () => false }))
import { UsageLimitPopup } from './UsageLimitPopup'
import {
  showUsageLimit,
  dismissUsageLimit,
  __resetUsageLimitSession
} from '../../../lib/usageLimit'
afterEach(() => {
  cleanup()
  __resetUsageLimitSession()
  sink.mockClear()
})
it('an observed limit is not a view or block until its UI mounts; rerenders do not count', () => {
  showUsageLimit('transcription')
  expect(sink.mock.calls.map(([id]) => id)).toEqual(['allowanceReached'])
  const tree = render(
    <MemoryRouter>
      <UsageLimitPopup />
    </MemoryRouter>
  )
  expect(sink.mock.calls.map(([id]) => id)).toEqual([
    'allowanceReached',
    'paywallViewed',
    'allowanceBlockShown'
  ])
  tree.rerender(
    <MemoryRouter>
      <UsageLimitPopup />
    </MemoryRouter>
  )
  expect(sink).toHaveBeenCalledTimes(3)
  act(() => dismissUsageLimit())
  act(() => showUsageLimit('transcription'))
  expect(sink.mock.calls.filter(([id]) => id === 'paywallViewed')).toHaveLength(2)
  expect(sink.mock.calls.filter(([id]) => id === 'allowanceBlockShown')).toHaveLength(2)
  expect(sink.mock.calls.filter(([id]) => id === 'allowanceReached')).toHaveLength(1)
})
it('optimistic local refusal may show its existing UI, but is not an authoritative allowance block', () => {
  render(
    <MemoryRouter>
      <UsageLimitPopup />
    </MemoryRouter>
  )
  act(() => showUsageLimit('chat', false))
  expect(sink.mock.calls.map(([id]) => id)).toEqual(['paywallViewed'])
})
