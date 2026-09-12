// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, screen, act } from '@testing-library/react'
import {
  getHubKnows,
  registerHubKnows,
  reportHubKnowsPresence,
  useHubKnowsPresence
} from './hubKnowsSlot'

function Probe(): React.JSX.Element {
  return <span data-testid="p">{String(useHubKnowsPresence())}</span>
}

afterEach(() => {
  cleanup()
  reportHubKnowsPresence(false)
})

describe('hubKnowsSlot', () => {
  it('registration is read back at render time', () => {
    const Component = (): React.JSX.Element => <div />
    registerHubKnows(Component)
    expect(getHubKnows()).toBe(Component)
  })

  it('presence notifies subscribers and dedupes repeat reports', () => {
    render(<Probe />)
    expect(screen.getByTestId('p').textContent).toBe('false')
    act(() => reportHubKnowsPresence(true))
    expect(screen.getByTestId('p').textContent).toBe('true')
    act(() => reportHubKnowsPresence(true)) // no-op, must not thrash
    expect(screen.getByTestId('p').textContent).toBe('true')
    act(() => reportHubKnowsPresence(false))
    expect(screen.getByTestId('p').textContent).toBe('false')
  })
})
