// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { PageHeader } from './PageHeader'

afterEach(cleanup)

describe('PageHeader', () => {
  it('renders the title, subtitle, and actions', () => {
    render(
      <PageHeader title="Conversations" subtitle="3 conversations" actions={<button>New</button>} />
    )
    expect(screen.getByRole('heading', { name: 'Conversations' })).toBeTruthy()
    expect(screen.getByText('3 conversations')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'New' })).toBeTruthy()
  })

  it('is seamless — no pill container (no border/background/shadow box) around the header', () => {
    const { container } = render(<PageHeader title="Conversations" />)
    // The old `.panel-header` pill (rounded border + tertiary fill + shadow) was
    // removed so the header sits directly on the page background. Guard against it
    // creeping back in.
    expect(container.querySelector('.panel-header')).toBeNull()
  })
})
