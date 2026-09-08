// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { SelectionActionBar } from './SelectionActionBar'

afterEach(cleanup)

function bar(selectedCount: number, mergeableCount: number): void {
  render(
    <SelectionActionBar
      selectedCount={selectedCount}
      mergeableCount={mergeableCount}
      allSelected={false}
      onToggleSelectAll={vi.fn()}
      onMerge={vi.fn()}
      onDelete={vi.fn()}
      deleting={false}
    />
  )
}

describe('SelectionActionBar', () => {
  it('renders an enabled Merge at full strength (never dimmed like a disabled one)', () => {
    bar(2, 2)
    const merge = screen.getByRole('button', { name: /Merge/ })
    expect(merge.hasAttribute('disabled')).toBe(false)
    expect(merge.className).not.toContain('opacity-40')
    expect(merge.className).toContain('text-white')
  })

  it('dims and disables Merge below 2 mergeable conversations', () => {
    bar(1, 1)
    const merge = screen.getByRole('button', { name: /Merge/ })
    expect(merge.hasAttribute('disabled')).toBe(true)
    expect(merge.className).toContain('opacity-40')
  })
})
