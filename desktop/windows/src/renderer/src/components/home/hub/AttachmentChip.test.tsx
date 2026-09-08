// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { AttachmentChip } from './AttachmentChip'
import type { PendingAttachment } from '../../../lib/chatAttachments'

const att = (over: Partial<PendingAttachment>): PendingAttachment => ({
  id: 'a1',
  name: 'file.png',
  mimeType: 'image/png',
  size: 100,
  status: 'uploaded',
  ...over
})

afterEach(cleanup)

describe('AttachmentChip', () => {
  it('shows the file name and removes on the button', () => {
    const onRemove = vi.fn()
    render(<AttachmentChip attachment={att({ name: 'notes.txt' })} onRemove={onRemove} />)
    expect(screen.getByText('notes.txt')).not.toBeNull()
    fireEvent.click(screen.getByLabelText('Remove notes.txt'))
    expect(onRemove).toHaveBeenCalledTimes(1)
  })

  it('surfaces a failed upload in the title, so it is not a silent no-op', () => {
    render(<AttachmentChip attachment={att({ name: 'x.pdf', status: 'failed' })} onRemove={() => {}} />)
    expect(screen.getByText('x.pdf').getAttribute('title')).toMatch(/upload failed/i)
  })
})
