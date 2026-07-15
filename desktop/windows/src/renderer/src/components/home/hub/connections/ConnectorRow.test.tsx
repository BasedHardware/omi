// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { Mail } from 'lucide-react'
import { ConnectorRow, PillButton } from './ConnectorRow'

afterEach(cleanup)

describe('ConnectorRow', () => {
  it('renders the icon row with title, description, action, and optional body', () => {
    render(
      <ConnectorRow
        icon={Mail}
        title="Email"
        description="Import email history."
        action={<PillButton tone="primary">Connect</PillButton>}
      >
        <p>expanded body</p>
      </ConnectorRow>
    )
    expect(screen.getByText('Email')).toBeTruthy()
    expect(screen.getByText('Import email history.')).toBeTruthy()
    expect(screen.getByText('Connect')).toBeTruthy()
    expect(screen.getByText('expanded body')).toBeTruthy()
  })

  it('derives a stable testid from the title', () => {
    render(<ConnectorRow icon={Mail} title="Sticky Notes" description="d" />)
    expect(screen.getByTestId('connector-sticky-notes')).toBeTruthy()
  })
})
