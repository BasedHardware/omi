// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { PlanGrid } from './PlanGrid'

afterEach(cleanup)

it.each([
  ['unlimited_v2', 'Stale title', 'Omi Pro'],
  ['operator', 'Stale title', 'Operator'],
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

it('keeps the selected Omi Pro card billing interval and checkout price identity', () => {
  const onBuy = vi.fn()
  render(
    <PlanGrid
      plans={[
        {
          id: 'unlimited_v2',
          title: 'Unlimited',
          prices: [{ id: 'fixture-price', title: 'Monthly', price_string: '$20' }]
        }
      ]}
      sub={{ plan: 'basic', status: 'active' }}
      selectedId="unlimited_v2"
      onSelect={vi.fn()}
      activePriceId={null}
      onBuy={onBuy}
    />
  )
  expect(screen.getByText('Omi Pro')).toBeTruthy()
  expect(screen.queryByText('Unlimited')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Monthly.*\$20/ }))
  expect(onBuy).toHaveBeenCalledWith('fixture-price', undefined)
})
