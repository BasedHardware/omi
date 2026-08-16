// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { MoveToFolderMenu } from './MoveToFolderMenu'
import type { ConversationFolder } from '../../../../shared/types'

afterEach(cleanup)

function folder(id: string, name: string): ConversationFolder {
  return {
    id,
    name,
    color: '#3b82f6',
    icon: null,
    orderIdx: 0,
    isSystem: false,
    conversationCount: 0,
    updatedAt: null
  }
}

const FOLDERS = [folder('w', 'Work'), folder('p', 'Personal'), folder('r', 'Research')]

function open(currentFolderId: string | null = null, onMove = vi.fn()): void {
  render(
    // Mirrors the row's hover action group: an opacity-0 container. The menu must
    // be portaled OUT of it — inside, an open menu faded away with the group the
    // moment the pointer left the row (the PR5 "transparent, clipped menu" bug).
    <div className="opacity-0">
      <MoveToFolderMenu folders={FOLDERS} currentFolderId={currentFolderId} onMove={onMove} />
    </div>
  )
  fireEvent.click(screen.getByLabelText('Move to folder'))
}

describe('MoveToFolderMenu', () => {
  it('lists every folder, including the row’s current one (ticked)', () => {
    open('p')
    const menu = screen.getByRole('menu', { name: 'Move to folder' })
    for (const name of ['Work', 'Personal', 'Research']) {
      expect(menu.textContent).toContain(name)
    }
    expect(menu.textContent).toContain('Remove from folder')
  })

  it('omits "Remove from folder" when the row is unfiled', () => {
    open(null)
    expect(screen.getByRole('menu').textContent).not.toContain('Remove from folder')
  })

  it('renders the panel in a body portal, not inside the hover-opacity group', () => {
    open('w')
    const menu = screen.getByRole('menu')
    expect(menu.closest('.opacity-0')).toBeNull()
    expect(menu.parentElement).toBe(document.body)
  })

  it('moves the conversation and closes on select', () => {
    const onMove = vi.fn()
    open('w', onMove)
    fireEvent.click(screen.getByRole('menuitem', { name: /Research/ }))
    expect(onMove).toHaveBeenCalledWith('r')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('closes on Escape', () => {
    open('w')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
  })
})
