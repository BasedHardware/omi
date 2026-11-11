// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { BrandImage } from './BrandImage'

afterEach(() => cleanup())

describe('BrandImage — broken-image resilience', () => {
  it('retries once with a cache-bust before giving up (recovers a transient 404)', () => {
    const { container } = render(<BrandImage src="/x/omi-mark.png" alt="Omi" />)
    const img = container.querySelector('img')!
    expect(img.getAttribute('src')).toBe('/x/omi-mark.png')

    // First failure → same asset, cache-busted (dev-server 404 recovery).
    fireEvent.error(img)
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/x/omi-mark.png?r=1')
  })

  it('falls back to an inline mark (never a broken <img>) after the retry also fails', () => {
    const { container } = render(<BrandImage src="/x/omi-mark.png" alt="Omi" />)
    fireEvent.error(container.querySelector('img')!)
    fireEvent.error(container.querySelector('img')!)
    // No <img> remains — an inline SVG placeholder stands in.
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('honors a caller-supplied fallback', () => {
    const { container, getByTestId } = render(
      <BrandImage src="/x/logo.png" fallback={<span data-testid="fb">omi</span>} />
    )
    fireEvent.error(container.querySelector('img')!)
    fireEvent.error(container.querySelector('img')!)
    expect(getByTestId('fb')).toBeTruthy()
  })
})
