import { Memory as MemoryType } from '@/src/types/memory.types';
import { SearchParamsTypes } from '@/src/types/params.types';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import {
  avatarToneIndex,
  durationMinutes,
  formatDuration,
  meetingTypeLabel,
  participantDisplayName,
  participantInitials,
  shareDateTime,
  sortParticipants,
} from '@/src/lib/shared-note.mjs';
import MemoryWithTabs from './summary/memory-with-tabs';
import { Fragment } from 'react';

interface MemoryProps {
  memory: MemoryType;
  searchParams: SearchParamsTypes;
}

export default function Memory({ memory }: MemoryProps) {
  const title = memory.structured?.title || DEFAULT_TITLE_MEMORY;
  const stamp = shareDateTime(memory);
  const minutes = durationMinutes(memory.started_at, memory.finished_at);
  const duration = minutes && minutes > 0 ? formatDuration(minutes) : '';
  const typeLabel = meetingTypeLabel(memory.structured?.meeting_type);
  const participants = sortParticipants(memory.structured?.participants);
  const metaItems = [
    stamp ? (
      <time key="time" dateTime={stamp.iso}>
        {stamp.label}
      </time>
    ) : null,
    duration ? <span key="duration">{duration}</span> : null,
    typeLabel ? <span key="type">{typeLabel}</span> : null,
  ].filter(Boolean);

  return (
    <div>
      {/* Content */}
      <div>
        <h1 className="sn-title">{title}</h1>
        {metaItems.length > 0 && (
          <div className="sn-meta">
            {metaItems.map((item, index) => (
              <Fragment key={index}>
                {index > 0 && (
                  <span className="sn-meta-sep" aria-hidden="true">
                    ·
                  </span>
                )}
                {item}
              </Fragment>
            ))}
          </div>
        )}
        {participants.length > 0 && (
          <ul className="sn-participants" aria-label="Participants">
            {participants.map((participant, index) => {
              const name = participantDisplayName(participant);
              const role =
                typeof participant.role === 'string' ? participant.role.trim() : '';
              return (
                <li key={index} className="sn-chip" title={role || undefined}>
                  <span
                    className={`sn-avatar sn-avatar-${avatarToneIndex(name)}`}
                    aria-hidden="true"
                  >
                    {participantInitials(name)}
                  </span>
                  <span className="sn-chip-text">
                    <span className="sn-chip-name">
                      {name}
                      {participant.is_ai_agent ? <span className="sn-ai">AI</span> : null}
                    </span>
                    {role ? <span className="sn-chip-role">{role}</span> : null}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <MemoryWithTabs memory={memory} />
    </div>
  );
}
