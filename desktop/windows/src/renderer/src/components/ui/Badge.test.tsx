// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { Badge } from './Badge'

afterEach(() => cleanup())

describe('Badge', () => {
  it('renders its label', () => {
    const { getByText } = render(<Badge>New</Badge>)
    expect(getByText('New')).toBeTruthy()
  })

  it('maps a tone to the status token classes', () => {
    const { getByText } = render(<Badge tone="warning">3</Badge>)
    const el = getByText('3')
    expect(el.className).toContain('text-warning')
    expect(el.className).toContain('bg-warning/15')
  })
})
