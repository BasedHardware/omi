// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConversationListRow } from './ConversationListRow'
import type { ConversationRow } from '../../lib/pageCache'
import type { ConversationFolder } from '../../../../shared/types'

afterEach(cleanup)

function folder(over: Partial<ConversationFolder> = {}): ConversationFolder {
  return {
    id: 'f1',
    name: 'Work',
    orderIdx: 0,
    isSystem: false,
    conversationCount: 0,
    ...over
  }
}

// Like renderRow, but exposes the callback mocks so a test can assert an action
// fired (and lets a row open the right-click menu — only the normal-row branch does).
function renderRowWithHandlers(
  row: Partial<ConversationRow>,
  opts: { selectMode?: boolean; folders?: ConversationFolder[] } = {}
): {
  onMoveToFolder: ReturnType<typeof vi.fn>
  onDelete: ReturnType<typeof vi.fn>
  onRename: ReturnType<typeof vi.fn>
} {
  const handlers = {
    onToggleSelect: vi.fn(),
    onStar: vi.fn(),
    onMoveToFolder: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn()
  }
  render(
    <MemoryRouter>
      <ConversationListRow
        row={{ ...BASE, ...row }}
        folders={opts.folders ?? []}
        selectMode={opts.selectMode ?? false}
        selected={false}
        {...handlers}
      />
    </MemoryRouter>
  )
  return handlers
}

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

describe('ConversationListRow right-click context menu', () => {
  const openMenu = (): void => {
    fireEvent.contextMenu(screen.getByRole('link'), { clientX: 40, clientY: 40 })
  }

  it('opens on right-click with the full Mac item set for a cloud row', () => {
    renderRowWithHandlers({})
    openMenu()
    expect(screen.getByRole('menu', { name: 'Conversation actions' })).toBeTruthy()
    for (const name of ['Copy Transcript', 'Copy Link', 'Edit Title', 'Move to Folder', 'Delete']) {
      expect(screen.getByRole('menuitem', { name })).toBeTruthy()
    }
  })

  it('omits the cloud-only items (Copy Link, Move to Folder) for a local row', () => {
    renderRowWithHandlers({ id: 'local-1', source: 'local' })
    openMenu()
    // Copy Transcript / Edit Title / Delete stay available for local rows.
    expect(screen.getByRole('menuitem', { name: 'Copy Transcript' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Edit Title' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeTruthy()
    expect(screen.queryByRole('menuitem', { name: 'Copy Link' })).toBeNull()
    expect(screen.queryByRole('menuitem', { name: 'Move to Folder' })).toBeNull()
  })

  it('Delete invokes onDelete with the row', () => {
    const h = renderRowWithHandlers({})
    openMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))
    expect(h.onDelete).toHaveBeenCalledTimes(1)
    expect(h.onDelete.mock.calls[0][0]).toMatchObject({ id: 'c1' })
  })

  it('Edit Title enters the inline rename and closes the menu', () => {
    renderRowWithHandlers({})
    openMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit Title' }))
    expect(screen.getByDisplayValue('Q3 roadmap sync')).toBeTruthy()
    expect(screen.queryByRole('menu', { name: 'Conversation actions' })).toBeNull()
  })

  it('Move to Folder submenu files the row into the chosen folder', () => {
    const h = renderRowWithHandlers({}, { folders: [folder({ id: 'f1', name: 'Work' })] })
    openMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Move to Folder' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Work' }))
    expect(h.onMoveToFolder).toHaveBeenCalledWith(expect.objectContaining({ id: 'c1' }), 'f1')
  })

  it('closes on Escape', () => {
    renderRowWithHandlers({})
    openMenu()
    fireEvent.keyDown(screen.getByRole('menu', { name: 'Conversation actions' }), { key: 'Escape' })
    expect(screen.queryByRole('menu', { name: 'Conversation actions' })).toBeNull()
  })

  it('does not open in select mode (the row is a checkbox button, not a link)', () => {
    renderRowWithHandlers({}, { selectMode: true })
    expect(screen.queryByRole('link')).toBeNull()
    fireEvent.contextMenu(screen.getByRole('button'))
    expect(screen.queryByRole('menu', { name: 'Conversation actions' })).toBeNull()
  })
})
