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
  addAttachments.mockReset()
  addAttachments.mockReturnValue({ accepted: [], rejected: [] })
  removeAttachment.mockClear()
  filesToPickedChatFiles.mockReset()
  ;(window as unknown as { omi: unknown }).omi = {
    openChatFiles: vi
      .fn()
      .mockResolvedValue([
        { name: 'a.png', mimeType: 'image/png', size: 3, bytes: new Uint8Array([1]) }
      ])
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

  it('does NOT offer Send when the only attachments have all FAILED and text is empty', () => {
    // A failed-only set would post an empty message; the button must not invite it.
    mockPending = [att({ id: 'x1', status: 'failed' })]
    renderBar({ value: '' })
    expect(screen.queryByLabelText('Send')).toBeNull()
  })

  it('surfaces a note when the attachment layer rejects files (not a silent drop)', async () => {
    addAttachments.mockReturnValue({
      accepted: [],
      rejected: [{ name: 'huge.zip', reason: 'too_large' }]
    })
    renderBar()
    fireEvent.click(screen.getByLabelText('Attach files'))
    await waitFor(() => expect(screen.getByText(/25 MB/)).not.toBeNull())
  })
})

describe('HubAskBar — whole-pill hit target (Mac contentShape parity)', () => {
  // Regression for the reported bug: only the input's own thin text line was
  // clickable, so a click on the pill's top/bottom strip or side padding did
  // nothing. The pill's mousedown now seats focus in the input wherever it lands,
  // while the paperclip and Connect/Send button keep their own actions.
  it('focuses the input when the pill body (not the text line) is pressed', async () => {
    renderBar()
    const input = screen.getByLabelText('Ask omi anything')
    const pill = input.parentElement as HTMLElement
    expect(document.activeElement).not.toBe(input)
    fireEvent.mouseDown(pill)
    // The handler defers the focus one frame (see HubAskBar: a sync focus inside a
    // preventDefault'd mousedown is swallowed by the browser), so wait for it to land.
    await waitFor(() => expect(document.activeElement).toBe(input))
  })

  // Focus is rAF-deferred, so a synchronous negative assert would pass even with
  // the button exclusion deleted — flush two frames before asserting.
  const flushFocusFrame = (): Promise<void> =>
    new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))

  it('does NOT hijack focus when the paperclip button is pressed (button keeps its action)', async () => {
    renderBar()
    const input = screen.getByLabelText('Ask omi anything')
    fireEvent.mouseDown(screen.getByLabelText('Attach files'))
    await flushFocusFrame()
    expect(document.activeElement).not.toBe(input)
  })

  it('does NOT hijack focus when the Connect button is pressed', async () => {
    renderBar()
    const input = screen.getByLabelText('Ask omi anything')
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Connect' }))
    await flushFocusFrame()
    expect(document.activeElement).not.toBe(input)
  })
})
