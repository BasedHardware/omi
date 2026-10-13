// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { PlanGrid } from './PlanGrid'

afterEach(cleanup)

it.each([
  ['operator', 'Operator', 'Pro'],
  ['architect', 'Stale title', 'Architect'],
  ['future_plan', 'Free', 'Plan unavailable']
])('uses plan identity %s for the card and selection button', (id, title, label) => {
  const onSelect = vi.fn()
  render(
    <PlanGrid
      plans={[
        { id, title, prices: [{ id: 'fixture-price', title: 'Monthly', price_string: '$20' }] }
      ]}
      sub={{ plan: 'basic', status: 'active' }}
      selectedId={null}
      onSelect={onSelect}
      activePriceId={null}
      onBuy={vi.fn()}
    />
  )
  expect(screen.getByText(label)).toBeTruthy()
  expect(screen.queryByText(title)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: `Select ${label}` }))
  expect(onSelect).toHaveBeenCalledWith(id)
})

it('keeps the selected Pro card billing interval and checkout price identity', () => {
  const onBuy = vi.fn()
  render(
    <PlanGrid
      plans={[
        {
          id: 'operator',
          title: 'Operator',
          prices: [{ id: 'fixture-price', title: 'Monthly', price_string: '$20' }]
        }
      ]}
      sub={{ plan: 'basic', status: 'active' }}
      selectedId="operator"
      onSelect={vi.fn()}
      activePriceId={null}
      onBuy={onBuy}
    />
  )
  expect(screen.getByText('Pro')).toBeTruthy()
  expect(screen.queryByText('Operator')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Monthly.*\$20/ }))
  expect(onBuy).toHaveBeenCalledWith('fixture-price', undefined)
})
