'use client';

import { TranscriptSegment, Person } from '@/src/types/memory.types';
import { avatarToneIndex, participantInitials } from '@/src/lib/shared-note.mjs';
import { useState } from 'react';

const PREVIEW_CHARS = 600;

export default function TranscriptionSegment({
  segment,
  people,
}: {
  segment: TranscriptSegment;
  people?: Person[];
}) {
  const [showMore, setShowMore] = useState(false);

  const textFormatted =
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').charAt(0).toUpperCase() +
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').slice(1);

  const isUser = segment.is_user;

  // Get person name if available
  const personName =
    segment.person_id && people
      ? people.find((p) => p.id === segment.person_id)?.name
      : null;

  const displayName = isUser ? 'Owner' : personName || `Speaker ${segment.speaker_id}`;
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
        <p className="sn-seg-name">{displayName}</p>
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
