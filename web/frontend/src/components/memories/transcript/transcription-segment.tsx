'use client';

import { TranscriptSegment } from '@/src/types/memory.types';
import {
  avatarToneIndex,
  participantInitials,
  transcriptTimestamp,
} from '@/src/lib/shared-note.mjs';
import { useState, useEffect, useRef } from 'react';

const PREVIEW_CHARS = 600;

export default function TranscriptionSegment({
  segment,
  displayName,
  sourceRequest,
}: {
  segment: TranscriptSegment;
  displayName: string;
  sourceRequest?: { id: string; request: number } | null;
}) {
  const rowRef = useRef<HTMLLIElement>(null);
  const [highlighted, setHighlighted] = useState(false);
  useEffect(() => {
    if (!sourceRequest) return;
    setHighlighted(true);
    setShowMore(true);
    rowRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    rowRef.current?.focus({ preventScroll: true });
    const timer = setTimeout(() => setHighlighted(false), 2500);
    return () => clearTimeout(timer);
  }, [sourceRequest]);
  const [showMore, setShowMore] = useState(false);

  const textFormatted =
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').charAt(0).toUpperCase() +
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').slice(1);

  const isUser = segment.is_user;

  const isLong = textFormatted.length > PREVIEW_CHARS;

  return (
    <li
      ref={rowRef}
      tabIndex={-1}
      className={`sn-seg${highlighted ? ' sn-seg-source' : ''}`}
    >
      <span
        className={`sn-avatar ${
          isUser ? 'sn-avatar-owner' : `sn-avatar-${avatarToneIndex(displayName)}`
        }`}
        aria-hidden="true"
      >
        {participantInitials(displayName)}
      </span>
      <div style={{ minWidth: 0 }}>
        <p className="sn-seg-name">
          {displayName}{' '}
          <span className="sn-muted">[{transcriptTimestamp(segment.start)}]</span>
        </p>
        <p className="sn-seg-text">
          {showMore || !isLong
            ? textFormatted
            : `${textFormatted.slice(0, PREVIEW_CHARS)}…`}{' '}
          {isLong && (
            <button
              type="button"
              onClick={() => setShowMore(!showMore)}
              className="sn-link"
            >
              {showMore ? 'Show less' : 'Show more'}
            </button>
          )}
        </p>
      </div>
    </li>
  );
}
