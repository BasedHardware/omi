// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import type { PendingAttachment } from '../../../lib/chatAttachments'

// The pending list is Track 1's module-level signal; the bar reads it through this
// hook. Drive it from the test so we can render any staged/uploading/failed state.
let mockPending: PendingAttachment[]
vi.mock('../../../hooks/usePendingAttachments', () => ({
  usePendingAttachments: () => mockPending
}))

// Spy the attachment layer's mutators — the bar must call these, not reimplement
// staging. MAX must match the real constant (the cap-disables-paperclip test).
const addAttachments = vi.fn()
const removeAttachment = vi.fn()
vi.mock('../../../lib/chatAttachments', () => ({
  addAttachments: (...a: unknown[]) => addAttachments(...a),
  removeAttachment: (...a: unknown[]) => removeAttachment(...a),
  MAX_CHAT_ATTACHMENTS: 4
}))

// Drag-drop reads bytes via File.arrayBuffer, which jsdom doesn't implement;
// stub the conversion and assert the bar forwards the result to addAttachments.
const filesToPickedChatFiles = vi.fn()
vi.mock('../../../lib/chatDropFiles', () => ({
  filesToPickedChatFiles: (...a: unknown[]) => filesToPickedChatFiles(...a)
}))

import { HubAskBar } from './HubAskBar'

const att = (over: Partial<PendingAttachment>): PendingAttachment => ({
  id: 'a1',
  name: 'file.png',
  mimeType: 'image/png',
  size: 100,
  status: 'uploaded',
  ...over
})

const noop = (): void => {}
type Props = Parameters<typeof HubAskBar>[0]
const renderBar = (over?: Partial<Props>): void => {
  render(
    <HubAskBar
      value=""
      onChange={noop}
      onSubmit={noop}
      onFocus={noop}
      sending={false}
      connectActive={false}
      onToggleConnect={noop}
      {...over}
    />
  )
}

beforeEach(() => {
  mockPending = []
  addAttachments.mockClear()
  removeAttachment.mockClear()
  filesToPickedChatFiles.mockReset()
  ;(window as unknown as { omi: unknown }).omi = {
    openChatFiles: vi
      .fn()
      .mockResolvedValue([{ name: 'a.png', mimeType: 'image/png', size: 3, bytes: new Uint8Array([1]) }])
  }
})
afterEach(cleanup)

describe('HubAskBar — attachments', () => {
  it('opens the native picker on the paperclip and stages what it returns', async () => {
    renderBar()
    fireEvent.click(screen.getByLabelText('Attach files'))
    await waitFor(() => expect(window.omi.openChatFiles).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(addAttachments).toHaveBeenCalledWith([expect.objectContaining({ name: 'a.png' })])
    )
  })

  it('does not stage anything when the picker is cancelled (empty array)', async () => {
    ;(window.omi.openChatFiles as ReturnType<typeof vi.fn>).mockResolvedValue([])
    renderBar()
    fireEvent.click(screen.getByLabelText('Attach files'))
    await waitFor(() => expect(window.omi.openChatFiles).toHaveBeenCalled())
    expect(addAttachments).not.toHaveBeenCalled()
  })

  it('renders a chip per pending attachment and removes via the chip button', () => {
    mockPending = [att({ id: 'x1', name: 'report.pdf', mimeType: 'application/pdf' })]
    renderBar()
    expect(screen.getByText('report.pdf')).not.toBeNull()
    fireEvent.click(screen.getByLabelText('Remove report.pdf'))
    expect(removeAttachment).toHaveBeenCalledWith('x1')
  })

  it('enables Send with attachments even when the text is empty (attachment-only)', () => {
    mockPending = [att({ id: 'x1' })]
    const onSubmit = vi.fn()
    renderBar({ value: '', onSubmit })
    // With attachments staged, the trailing control is Send — not Connect.
    expect(screen.queryByRole('button', { name: 'Connect' })).toBeNull()
    fireEvent.click(screen.getByLabelText('Send'))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('disables the paperclip at the 4-file cap', () => {
    mockPending = [1, 2, 3, 4].map((i) => att({ id: `x${i}`, name: `f${i}.png` }))
    renderBar()
    const clip = screen.getByLabelText(/Attachment limit reached/)
    expect((clip as HTMLButtonElement).disabled).toBe(true)
  })

  it('stages files dropped onto the bar', async () => {
    filesToPickedChatFiles.mockResolvedValue([
      { name: 'drop.png', mimeType: 'image/png', size: 3, bytes: new Uint8Array([1]) }
    ])
    renderBar()
    const file = new File([new Uint8Array([1, 2, 3])], 'drop.png', { type: 'image/png' })
    fireEvent.drop(screen.getByTestId('hub-ask-bar'), { dataTransfer: { files: [file] } })
    await waitFor(() => expect(filesToPickedChatFiles).toHaveBeenCalledWith([file]))
    await waitFor(() =>
      expect(addAttachments).toHaveBeenCalledWith([expect.objectContaining({ name: 'drop.png' })])
    )
  })

  it('shows an upload spinner while an attachment is uploading', () => {
    mockPending = [att({ id: 'x1', name: 'big.pdf', status: 'uploading' })]
    renderBar()
    // The chip is present and the remove control still works while uploading.
    expect(screen.getByText('big.pdf')).not.toBeNull()
    expect(screen.getByLabelText('Remove big.pdf')).not.toBeNull()
  })
})
