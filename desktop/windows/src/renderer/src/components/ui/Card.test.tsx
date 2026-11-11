// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { Card } from './Card'

afterEach(() => cleanup())

describe('Card', () => {
  it('renders children on the token surface', () => {
    const { getByText } = render(<Card>Body</Card>)
    const card = getByText('Body')
    expect(card.className).toContain('bg-[var(--bg-secondary)]')
    expect(card.className).toContain('rounded-[var(--radius-card)]')
  })

  it('adds a hover affordance when interactive', () => {
    const { getByText } = render(<Card interactive>Tap</Card>)
    expect(getByText('Tap').className).toContain('cursor-pointer')
  })
})
