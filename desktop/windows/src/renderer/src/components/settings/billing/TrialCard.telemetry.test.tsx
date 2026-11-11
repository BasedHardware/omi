// @vitest-environment jsdom
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { expect, it, vi, afterEach } from 'vitest'
const sink = vi.hoisted(() => vi.fn())
vi.mock('../../../lib/analytics', () => ({ trackPurchaseEvent: sink }))
import { TrialCard } from './TrialCard'
afterEach(() => {
  cleanup()
  sink.mockClear()
})
it('server trial expiry reaches once; its reminder never claims to block use', () => {
  const trial = {
    trial_expired: false,
    trial_duration_seconds: 300,
    trial_remaining_seconds: 200
  } as any
  const tree = render(<TrialCard trial={trial} onViewPlans={() => {}} />)
  expect(sink).not.toHaveBeenCalled()
  tree.rerender(<TrialCard trial={{ ...trial, trial_expired: true }} onViewPlans={() => {}} />)
  tree.rerender(<TrialCard trial={{ ...trial, trial_expired: true }} onViewPlans={() => {}} />)
  expect(sink.mock.calls.map(([id]) => id)).toEqual(['allowanceReached'])
  tree.rerender(<TrialCard trial={trial} onViewPlans={() => {}} />)
  tree.rerender(<TrialCard trial={{ ...trial, trial_expired: true }} onViewPlans={() => {}} />)
  expect(sink.mock.calls.map(([id]) => id)).toEqual(['allowanceReached', 'allowanceReached'])
})

it('the trial reminder forwards its existing action after a bounded upgrade intent', () => {
  const onViewPlans = vi.fn()
  render(<TrialCard trial={{ trial_expired: true } as any} onViewPlans={onViewPlans} />)
  sink.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'View Plans' }))
  expect(onViewPlans).toHaveBeenCalledOnce()
  expect(sink).toHaveBeenCalledWith('upgradeTapped', {
    plan: 'unknown',
    billing_interval: 'unknown',
    source: 'windows_billing'
  })
})
