// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConversationListRow } from './ConversationListRow'
import type { ConversationRow } from '../../lib/pageCache'

afterEach(cleanup)

const BASE: ConversationRow = {
  id: 'c1',
  title: 'Q3 roadmap sync',
  subtitle: '7/14/2026, 10:00:00 AM',
  preview: 'We agreed to cut the migration from the release and revisit in August.',
  source: 'cloud',
  sortAt: 1
}

function renderRow(row: Partial<ConversationRow>, selectMode = false, selected = false): void {
  render(
    <MemoryRouter>
      <ConversationListRow
        row={{ ...BASE, ...row }}
        folders={[]}
        selectMode={selectMode}
        selected={selected}
        onToggleSelect={vi.fn()}
        onStar={vi.fn()}
        onMoveToFolder={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />
    </MemoryRouter>
  )
}

describe('ConversationListRow', () => {
  it('shows the overview snippet under the title', () => {
    renderRow({})
    expect(screen.getByText(/cut the migration/)).toBeTruthy()
  })

  it('does not render placeholder previews as a snippet line', () => {
    renderRow({ preview: '(no transcript)' })
    expect(screen.queryByText('(no transcript)')).toBeNull()
  })

  it('paints a selected row with the purple tint (never bare like an unselected one)', () => {
    renderRow({}, true, true)
    const row = screen.getByRole('button', { pressed: true })
    expect(row.style.backgroundColor).toBe('rgba(139, 92, 246, 0.22)')
    // The tint is inline, so it beats both the surface and the hover background —
    // every selected row looks identical whether or not it's hovered.
    expect(row.style.borderColor).toContain('139, 92, 246')
  })

  it('leaves an unselected row untinted in select mode', () => {
    renderRow({}, true, false)
    const row = screen.getByRole('button', { pressed: false })
    expect(row.style.backgroundColor).toBe('')
  })
})
