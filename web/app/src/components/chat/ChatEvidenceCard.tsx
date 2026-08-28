'use client';

import type { ReactElement } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  CircleSlash,
  CloudOff,
  FileWarning,
  Loader2,
  type LucideIcon,
} from 'lucide-react';
import type { ChatEvidenceEnvelope, ChatEvidenceReference } from '@/lib/chatEvidence';

type EvidenceStatus = {
  label: string;
  Icon: LucideIcon;
  className: string;
};

const KIND_LABELS: Record<ChatEvidenceReference['kind'], string> = {
  conversation_summary: 'Conversation summary',
  conversation_segment: 'Conversation segment',
  screen: 'Screen',
  keyframe: 'Keyframe',
  request: 'Request',
};

function statusFor(state: ChatEvidenceReference['state']): EvidenceStatus {
  switch (state) {
    case 'available':
      return { label: 'Available', Icon: CheckCircle2, className: 'text-emerald-300' };
    case 'loading':
      return { label: 'Loading', Icon: Loader2, className: 'text-text-secondary' };
    case 'offline':
      return {
        label: 'Unavailable offline',
        Icon: CloudOff,
        className: 'text-amber-300',
      };
    case 'pruned':
      return {
        label: 'No longer available',
        Icon: CircleSlash,
        className: 'text-text-quaternary',
      };
    case 'failed':
      return { label: 'Failed to load', Icon: AlertCircle, className: 'text-red-300' };
    case 'unknown':
      return {
        label: 'Unavailable',
        Icon: FileWarning,
        className: 'text-text-quaternary',
      };
  }
}

function ChatEvidenceReferenceCard({ reference }: { reference: ChatEvidenceReference }) {
  const { label: statusLabel, Icon, className: statusClass } = statusFor(reference.state);
  const kindLabel = KIND_LABELS[reference.kind];
  const title = reference.title || kindLabel;

  return (
    <article
      aria-label={`${title}, ${statusLabel}`}
      className="flex w-fit max-w-[85%] flex-col gap-1 rounded-xl border border-stroke bg-bg-secondary/60 px-3.5 py-2.5"
      data-testid={`chat-evidence-${reference.id}`}
    >
      <div className="flex items-center gap-2">
        <span className="truncate text-[13px] font-medium text-text-primary">
          {title}
        </span>
        <span
          className={`ml-auto flex shrink-0 items-center gap-1 text-[11px] ${statusClass}`}
        >
          <Icon
            aria-hidden="true"
            className={`h-3.5 w-3.5 ${reference.state === 'loading' ? 'animate-spin' : ''}`}
          />
          <span>{statusLabel}</span>
        </span>
      </div>
      {reference.summary ? (
        <p className="line-clamp-3 text-[12px] leading-snug text-text-secondary">
          {reference.summary}
        </p>
      ) : null}
    </article>
  );
}

/** Supplemental, non-actionable evidence chrome for an assistant answer. */
export function ChatEvidenceCard({
  envelope,
}: {
  envelope: ChatEvidenceEnvelope | null;
}): ReactElement | null {
  if (!envelope || envelope.references.length === 0) return null;

  return (
    <section aria-label="Supporting evidence" className="mt-2 flex flex-col gap-1.5">
      {envelope.references.map((reference, index) => (
        <ChatEvidenceReferenceCard
          key={`${reference.id}-${index}`}
          reference={reference}
        />
      ))}
    </section>
  );
}
