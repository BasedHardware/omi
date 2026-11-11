import {
  AlertCircle,
  CheckCircle2,
  CircleSlash,
  CloudOff,
  FileWarning,
  Loader2,
  type LucideIcon
} from 'lucide-react'
import {
  type ChatEvidenceReference,
  type ChatEvidenceReferenceEnvelope
} from '../../../../shared/knowledgeLedger'

type EvidenceStatus = {
  label: string
  Icon: LucideIcon
  className: string
}

const KIND_LABELS: Record<ChatEvidenceReference['kind'], string> = {
  conversation_summary: 'Conversation summary',
  conversation_segment: 'Conversation segment',
  screen: 'Screen evidence',
  keyframe: 'Screen keyframe',
  request: 'Evidence request',
  unknown: 'Evidence'
}

function statusFor(reference: ChatEvidenceReference): EvidenceStatus {
  switch (reference.state) {
    case 'available':
      return { label: 'Available', Icon: CheckCircle2, className: 'text-emerald-300' }
    case 'loading':
      return { label: 'Loading', Icon: Loader2, className: 'text-white/60' }
    case 'offline':
      return { label: 'Unavailable offline', Icon: CloudOff, className: 'text-amber-300' }
    case 'pruned':
      return { label: 'No longer available', Icon: CircleSlash, className: 'text-white/50' }
    case 'failed':
      return { label: 'Failed to load', Icon: AlertCircle, className: 'text-red-300' }
    case 'unknown':
      return { label: 'Unavailable', Icon: FileWarning, className: 'text-white/50' }
  }
}

/**
 * Supplemental evidence chrome for a chat answer. Evidence is deliberately
 * non-actionable on Windows until the cross-client privacy and Rewind
 * navigation contracts are ratified; the answer text remains authoritative.
 */
export function ChatEvidenceReferenceCard({
  reference,
  compact = false
}: {
  reference: ChatEvidenceReference
  compact?: boolean
}): React.JSX.Element {
  const { label: statusLabel, Icon, className: statusClass } = statusFor(reference)
  const kindLabel = KIND_LABELS[reference.kind]
  const title = reference.title?.trim() || kindLabel
  const summary = reference.summary?.trim()
  const error = reference.state === 'failed' ? reference.errorMessage?.trim() : undefined
  const padding = compact ? 'px-3 py-2' : 'px-3.5 py-2.5'

  return (
    <article
      aria-label={`${title}, ${statusLabel}`}
      className={`flex w-fit max-w-[85%] flex-col gap-1 rounded-xl border border-white/10 bg-white/[0.035] ${padding}`}
      data-testid={`chat-evidence-${reference.id || 'unknown'}`}
    >
      <div className="flex items-center gap-2">
        <span className="truncate text-[13px] font-medium text-white/85">{title}</span>
        <span className={`ml-auto flex shrink-0 items-center gap-1 text-[11px] ${statusClass}`}>
          <Icon className={`h-3.5 w-3.5 ${reference.state === 'loading' ? 'animate-spin' : ''}`} />
          <span>{statusLabel}</span>
        </span>
      </div>
      {summary ? (
        <p className="line-clamp-3 text-[12px] leading-snug text-white/60">{summary}</p>
      ) : null}
      {error ? (
        <p className="line-clamp-2 text-[12px] leading-snug text-red-200/75">{error}</p>
      ) : null}
      {reference.state === 'unknown' ? (
        <p className="text-[11px] leading-snug text-white/45">
          This evidence is from an unsupported version and cannot be opened here.
        </p>
      ) : null}
    </article>
  )
}

/** Supplemental evidence list; empty/malformed envelopes render nothing. */
export function ChatEvidenceReferenceList({
  envelope,
  compact = false
}: {
  envelope: ChatEvidenceReferenceEnvelope
  compact?: boolean
}): React.JSX.Element | null {
  if (envelope.references.length === 0) return null
  return (
    <section aria-label="Supporting evidence" className="flex flex-col gap-1.5">
      {envelope.references.map((reference, index) => (
        <ChatEvidenceReferenceCard
          key={`${reference.id || 'unknown'}-${index}`}
          reference={reference}
          compact={compact}
        />
      ))}
    </section>
  )
}
