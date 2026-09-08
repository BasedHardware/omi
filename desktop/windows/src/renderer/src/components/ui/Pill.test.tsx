// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { Pill } from './Pill'

afterEach(() => cleanup())

describe('Pill', () => {
  it('renders a static label as a span', () => {
    const { getByText } = render(<Pill>Online</Pill>)
    expect(getByText('Online').closest('span')).toBeTruthy()
  })

  it('renders a button and fires onClick when interactive', () => {
    const onClick = vi.fn()
    const { getByRole } = render(
      <Pill dot onClick={onClick}>
        Live
      </Pill>
    )
    fireEvent.click(getByRole('button', { name: 'Live' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
