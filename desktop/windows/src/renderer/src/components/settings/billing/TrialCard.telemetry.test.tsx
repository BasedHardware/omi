// @vitest-environment jsdom
import { render, cleanup } from '@testing-library/react'
import { expect, it, vi, afterEach } from 'vitest'
const sink = vi.hoisted(() => vi.fn())
vi.mock('../../../lib/analytics', () => ({ trackPurchaseEvent: sink }))
import { TrialCard } from './TrialCard'
afterEach(() => {
  cleanup()
  sink.mockClear()
})
it('server trial expiry reaches once and only rendered expiry UI reports a block', () => {
  const trial = {
    trial_expired: false,
    trial_duration_seconds: 300,
    trial_remaining_seconds: 200
  } as any
  const tree = render(<TrialCard trial={trial} onViewPlans={() => {}} />)
  expect(sink).not.toHaveBeenCalled()
  tree.rerender(<TrialCard trial={{ ...trial, trial_expired: true }} onViewPlans={() => {}} />)
  tree.rerender(<TrialCard trial={{ ...trial, trial_expired: true }} onViewPlans={() => {}} />)
  expect(sink.mock.calls.map(([id]) => id)).toEqual(['allowanceReached', 'allowanceBlockShown'])
  tree.rerender(<TrialCard trial={trial} onViewPlans={() => {}} />)
  tree.rerender(<TrialCard trial={{ ...trial, trial_expired: true }} onViewPlans={() => {}} />)
  expect(sink.mock.calls.map(([id]) => id)).toEqual([
    'allowanceReached',
    'allowanceBlockShown',
    'allowanceReached',
    'allowanceBlockShown'
  ])
})
