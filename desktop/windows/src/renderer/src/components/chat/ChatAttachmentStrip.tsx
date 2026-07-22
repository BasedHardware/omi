import { useState } from 'react'
import { Braces, Code, File as FileIcon, FileText, Image as ImageIcon, Table } from 'lucide-react'
import type { ChatAttachment } from '../../../../shared/types'
import { cn } from '../../lib/utils'

/**
 * The files attached to a sent chat message, rendered above the user bubble
 * (Mac's ChatResourceStrip / ChatBubble). One vertical column — Mac found
 * side-by-side cards squeezed filenames into "d...ml", so attachments always
 * stack. Two card kinds:
 *   - Image (an `image/*` file with a public thumbnail URL) → a 140px tile with
 *     the image and a filename overlay; if the thumbnail fails to load it falls
 *     back to the document card.
 *   - Document (everything else) → an icon badge + filename + mimeType subtitle.
 * Non-interactive in v1 (no open/reveal/copy) — Windows keeps no local source
 * path after upload, so the cards are always in Mac's post-reload presentation.
 * All neutrals, zero accent color — consistent with the bubble styles.
 */
export function ChatAttachmentStrip({
  attachments,
  compact,
  align
}: {
  attachments: ChatAttachment[]
  compact: boolean
  align: 'start' | 'end'
}): React.JSX.Element | null {
  if (!attachments.length) return null
  return (
    <div
      className={cn(
        'flex flex-col gap-1.5',
        align === 'end' ? 'ml-auto items-end' : 'mr-auto items-start',
        compact ? 'max-w-[320px]' : 'max-w-[360px]'
      )}
    >
      {attachments.map((a, i) => (
        <AttachmentCard key={a.id ?? i} attachment={a} compact={compact} />
      ))}
    </div>
  )
}

/** Pick the document-card glyph for a mimeType (mirrors Mac's iconName map). */
function DocumentIcon({
  mimeType,
  className
}: {
  mimeType: string
  className: string
}): React.JSX.Element {
  const mt = mimeType.toLowerCase()
  if (mt.startsWith('image/')) return <ImageIcon className={className} strokeWidth={2} />
  if (mt === 'application/pdf') return <FileText className={className} strokeWidth={2} />
  if (mt.includes('json')) return <Braces className={className} strokeWidth={2} />
  if (mt === 'text/html' || mt === 'text/markdown')
    return <Code className={className} strokeWidth={2} />
  if (mt.includes('csv') || mt.includes('spreadsheet'))
    return <Table className={className} strokeWidth={2} />
  return <FileIcon className={className} strokeWidth={2} />
}

function AttachmentCard({
  attachment,
  compact
}: {
  attachment: ChatAttachment
  compact: boolean
}): React.JSX.Element {
  const [imageError, setImageError] = useState(false)
  const isImage = attachment.mimeType.toLowerCase().startsWith('image/')
  const showImage = isImage && !!attachment.thumbnailUrl && !imageError

  if (showImage) {
    return (
      <div
        className={cn(
          'relative w-full overflow-hidden border border-white/5 bg-white/[0.04]',
          compact ? 'h-[112px] rounded-xl' : 'h-[140px] rounded-[14px]'
        )}
      >
        <img
          src={attachment.thumbnailUrl}
          alt={attachment.name}
          className="h-full w-full object-cover"
          onError={() => setImageError(true)}
        />
        <div className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 bg-gradient-to-b from-transparent to-black/55 px-2.5 py-2">
          <ImageIcon className="h-[11px] w-[11px] shrink-0 text-white" strokeWidth={2} />
          <span className="truncate text-[11px] font-semibold text-white" title={attachment.name}>
            {attachment.name}
          </span>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'flex w-full items-center gap-2.5 border border-white/5 bg-white/[0.06]',
        compact ? 'rounded-xl px-2 py-1.5' : 'rounded-[14px] px-2.5 py-2'
      )}
    >
      <div
        className={cn(
          'flex shrink-0 items-center justify-center rounded-lg bg-white/[0.08] text-white/60',
          compact ? 'h-7 w-7' : 'h-9 w-9'
        )}
      >
        <DocumentIcon
          mimeType={attachment.mimeType}
          className={compact ? 'h-3.5 w-3.5' : 'h-4 w-4'}
        />
      </div>
      <div className="min-w-0 flex-1">
        <div
          className={cn(
            'truncate font-semibold text-white/90',
            compact ? 'text-[12px]' : 'text-[13px]'
          )}
          title={attachment.name}
        >
          {attachment.name}
        </div>
        <div className={cn('truncate text-white/40', compact ? 'text-[10px]' : 'text-[11px]')}>
          {attachment.mimeType}
        </div>
      </div>
    </div>
  )
}
