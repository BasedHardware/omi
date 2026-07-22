// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { Toggle } from './Toggle'

afterEach(() => cleanup())

describe('Toggle', () => {
  it('exposes switch role + checked state and flips on click', () => {
    const onChange = vi.fn()
    const { getByRole } = render(<Toggle checked={false} onChange={onChange} label="Wifi" />)
    const sw = getByRole('switch', { name: 'Wifi' })
    expect(sw.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(sw)
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('does not fire when disabled', () => {
    const onChange = vi.fn()
    const { getByRole } = render(<Toggle checked onChange={onChange} disabled />)
    fireEvent.click(getByRole('switch'))
    expect(onChange).not.toHaveBeenCalled()
  })
})
