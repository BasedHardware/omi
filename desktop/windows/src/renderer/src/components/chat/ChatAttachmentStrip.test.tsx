// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { ChatAttachmentStrip } from './ChatAttachmentStrip'
import type { ChatAttachment } from '../../../../shared/types'

const image: ChatAttachment = {
  id: 'img1',
  name: 'photo.png',
  mimeType: 'image/png',
  thumbnailUrl: 'https://cdn.omi/thumb.png'
}
const pdf: ChatAttachment = { id: 'doc1', name: 'report.pdf', mimeType: 'application/pdf' }

afterEach(cleanup)

describe('ChatAttachmentStrip', () => {
  it('renders nothing for an empty list', () => {
    const { container } = render(
      <ChatAttachmentStrip attachments={[]} compact={false} align="end" />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders an image tile with the thumbnail src and the filename', () => {
    render(<ChatAttachmentStrip attachments={[image]} compact={false} align="end" />)
    const img = screen.getByAltText('photo.png') as HTMLImageElement
    expect(img.tagName).toBe('IMG')
    expect(img.getAttribute('src')).toBe('https://cdn.omi/thumb.png')
    expect(screen.getByText('photo.png')).not.toBeNull()
    // Image tile has no mimeType subtitle (that is the document card only).
    expect(screen.queryByText('image/png')).toBeNull()
  })

  it('falls back to a document card when the thumbnail fails to load', () => {
    render(<ChatAttachmentStrip attachments={[image]} compact={false} align="end" />)
    fireEvent.error(screen.getByAltText('photo.png'))
    // No img anymore; the document card now shows the mimeType subtitle.
    expect(screen.queryByAltText('photo.png')).toBeNull()
    expect(screen.getByText('image/png')).not.toBeNull()
    expect(screen.getByText('photo.png')).not.toBeNull()
  })

  it('renders a non-image as a document card with name and mimeType', () => {
    render(<ChatAttachmentStrip attachments={[pdf]} compact={false} align="end" />)
    expect(screen.queryByAltText('report.pdf')).toBeNull()
    expect(screen.getByText('report.pdf')).not.toBeNull()
    expect(screen.getByText('application/pdf')).not.toBeNull()
  })

  it('renders an image without a thumbnail as a document card (no broken img)', () => {
    const noThumb: ChatAttachment = { id: 'i2', name: 'raw.png', mimeType: 'image/png' }
    render(<ChatAttachmentStrip attachments={[noThumb]} compact={false} align="end" />)
    expect(screen.queryByAltText('raw.png')).toBeNull()
    expect(screen.getByText('image/png')).not.toBeNull()
  })

  it('applies compact (bar) sizing to the container', () => {
    const { container } = render(<ChatAttachmentStrip attachments={[pdf]} compact align="end" />)
    expect((container.firstChild as HTMLElement).className).toContain('max-w-[320px]')
  })

  it('applies full (main) sizing by default', () => {
    const { container } = render(
      <ChatAttachmentStrip attachments={[pdf]} compact={false} align="end" />
    )
    expect((container.firstChild as HTMLElement).className).toContain('max-w-[360px]')
  })
})
