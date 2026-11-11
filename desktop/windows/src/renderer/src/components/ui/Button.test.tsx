// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { Button } from './Button'

afterEach(() => cleanup())

describe('Button', () => {
  it('renders its label and fires onClick', () => {
    const onClick = vi.fn()
    const { getByRole } = render(<Button onClick={onClick}>Save</Button>)
    const btn = getByRole('button', { name: 'Save' })
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('applies the danger variant fill', () => {
    const { getByRole } = render(<Button variant="danger">Delete</Button>)
    expect(getByRole('button').className).toContain('bg-[var(--error)]')
  })

  it('is disabled and non-interactive while loading', () => {
    const onClick = vi.fn()
    const { getByRole } = render(
      <Button loading onClick={onClick}>
        Saving
      </Button>
    )
    const btn = getByRole('button') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(onClick).not.toHaveBeenCalled()
  })
})
