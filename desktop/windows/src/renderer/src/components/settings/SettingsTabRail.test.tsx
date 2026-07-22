// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { SettingsTabRail } from './SettingsTabRail'

afterEach(cleanup)

function renderRail(): HTMLInputElement {
  render(
    <SettingsTabRail
      active="general"
      onSelect={vi.fn()}
      query=""
      onQuery={vi.fn()}
      onBack={vi.fn()}
    />
  )
  return screen.getByPlaceholderText('Search settings…') as HTMLInputElement
}

describe('SettingsTabRail search input focus indicator', () => {
  it('uses the app focus-ring utility so keyboard focus is visible', () => {
    expect(renderRail().className).toContain('focus-ring')
  })

  it('does not suppress the outline without a replacement indicator', () => {
    // `focus:outline-none` on its own left keyboard users with no focus cue.
    // `.focus-ring` supplies the visible indicator (and its own transparent
    // at-rest outline), so the bare suppressor must be gone.
    expect(renderRail().className).not.toContain('focus:outline-none')
  })
})
