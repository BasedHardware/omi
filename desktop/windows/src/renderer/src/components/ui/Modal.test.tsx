// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { Modal } from './Modal'

afterEach(() => cleanup())

describe('Modal', () => {
  it('renders title + body content when open (portaled)', () => {
    const { getByRole, getByText } = render(
      <Modal open onOpenChange={() => {}} title="Rename">
        Pick a new name
      </Modal>
    )
    expect(getByRole('dialog')).toBeTruthy()
    expect(getByText('Rename')).toBeTruthy()
    expect(getByText('Pick a new name')).toBeTruthy()
  })

  it('requests close on Esc when dismissible', () => {
    const onOpenChange = vi.fn()
    render(
      <Modal open onOpenChange={onOpenChange} title="Rename">
        Body
      </Modal>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('blocks Esc dismissal in the non-dismissible variant', () => {
    const onOpenChange = vi.fn()
    render(
      <Modal open onOpenChange={onOpenChange} title="Delete account" dismissible={false}>
        This cannot be undone
      </Modal>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  // Radix registers its outside-pointer listener inside a setTimeout(0), so let a
  // macrotask elapse before dispatching the pointerdown.
  const nextTick = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

  it('requests close on outside pointer-down when dismissible', async () => {
    const onOpenChange = vi.fn()
    render(
      <Modal open onOpenChange={onOpenChange} title="Rename">
        Body
      </Modal>
    )
    await nextTick()
    // A pointerdown landing outside the dialog content (on the scrim / page).
    fireEvent.pointerDown(document.body)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('blocks outside pointer-down dismissal in the non-dismissible variant', async () => {
    const onOpenChange = vi.fn()
    render(
      <Modal open onOpenChange={onOpenChange} title="Delete account" dismissible={false}>
        This cannot be undone
      </Modal>
    )
    await nextTick()
    fireEvent.pointerDown(document.body)
    expect(onOpenChange).not.toHaveBeenCalled()
  })
})
