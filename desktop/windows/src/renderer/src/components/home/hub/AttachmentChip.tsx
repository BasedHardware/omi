import { Loader2, Paperclip, TriangleAlert, X } from 'lucide-react'
import type { PendingAttachment } from '../../../lib/chatAttachments'
import { cn } from '../../../lib/utils'

// One pending-attachment chip, shown above the ask-bar pill while files are
// staged. It reflects the upload lifecycle from Track 1's attachment layer — a
// spinner while uploading, a warning tint if the upload failed — and carries a
// remove button. The chip is keyed upstream by the attachment's stable local id,
// so it survives status changes (uploading → uploaded/failed) without remounting.
export function AttachmentChip(props: {
  attachment: PendingAttachment
  onRemove: () => void
}): React.JSX.Element {
  const { attachment, onRemove } = props
  const failed = attachment.status === 'failed'
  const uploading = attachment.status === 'uploading'

  return (
    <div
      className={cn(
        'flex h-8 max-w-[190px] items-center gap-1.5 rounded-full border pl-2.5 pr-1',
        'text-[12px] font-medium',
        failed
          ? 'border-error/40 bg-error/[0.12] text-home-ink'
          : 'border-home-hairline bg-home-tile text-home-ink'
      )}
    >
      {uploading ? (
        <Loader2 className="h-3 w-3 shrink-0 animate-spin text-home-muted" strokeWidth={2.5} />
      ) : failed ? (
        <TriangleAlert className="h-3 w-3 shrink-0 text-error" strokeWidth={2.5} />
      ) : (
        <Paperclip className="h-3 w-3 shrink-0 text-home-muted" strokeWidth={2.5} />
      )}
      <span
        className="min-w-0 flex-1 truncate"
        title={failed ? `${attachment.name} — upload failed` : attachment.name}
      >
        {attachment.name}
      </span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${attachment.name}`}
        className={cn(
          'focus-ring flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
          'text-home-muted transition-colors duration-150 hover:bg-white/10 hover:text-home-ink'
        )}
      >
        <X className="h-3 w-3" strokeWidth={2.5} />
      </button>
    </div>
  )
}
