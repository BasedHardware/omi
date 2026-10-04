'use client';

import { TranscriptSegment } from '@/src/types/memory.types';
import {
  avatarToneIndex,
  participantInitials,
  transcriptTimestamp,
} from '@/src/lib/shared-note.mjs';
import { useState } from 'react';

const PREVIEW_CHARS = 600;

export default function TranscriptionSegment({
  segment,
  displayName,
}: {
  segment: TranscriptSegment;
  displayName: string;
}) {
  const [showMore, setShowMore] = useState(false);

  const textFormatted =
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').charAt(0).toUpperCase() +
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').slice(1);

  const isUser = segment.is_user;

  const isLong = textFormatted.length > PREVIEW_CHARS;

  return (
    <li className="sn-seg">
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
