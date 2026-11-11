'use client';

import { cn } from '@/lib/utils';
import {
  noteAvatarToneIndex,
  noteParticipantInitials,
  noteParticipantName,
  sortNoteParticipants,
  type NoteParticipantLike,
} from '@/lib/meetingNotes';

const AVATAR_TONES = [
  'bg-blue-500/15 text-blue-300',
  'bg-emerald-500/15 text-emerald-300',
  'bg-amber-500/15 text-amber-300',
  'bg-slate-500/15 text-slate-300',
  'bg-rose-500/15 text-rose-300',
  'bg-cyan-500/15 text-cyan-300',
];

interface NoteParticipantsProps {
  participants?: NoteParticipantLike[] | null;
}

export function NoteParticipants({ participants }: NoteParticipantsProps) {
  const sorted = sortNoteParticipants(participants);
  if (sorted.length === 0) return null;

  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Participants">
      {sorted.map((participant, index) => {
        const name = noteParticipantName(participant);
        const role = typeof participant.role === 'string' ? participant.role.trim() : '';
        return (
          <li
            key={index}
            title={role || undefined}
            className="flex max-w-full items-center gap-2 rounded-full border border-bg-quaternary/50 bg-bg-tertiary/50 py-1 pl-1 pr-2.5"
          >
            <span
              aria-hidden="true"
              className={cn(
                'flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-semibold',
                AVATAR_TONES[noteAvatarToneIndex(name) % AVATAR_TONES.length],
              )}
            >
              {noteParticipantInitials(name)}
            </span>
            <span className="flex min-w-0 flex-col leading-tight">
              <span className="flex items-center gap-1 break-all text-xs text-text-primary">
                {name}
                {participant.is_ai_agent ? (
                  <span className="rounded border border-bg-quaternary px-1 text-[9px] font-semibold leading-4 text-text-tertiary">
                    AI
                  </span>
                ) : null}
              </span>
              {role ? (
                <span className="max-w-[160px] truncate text-[10px] text-text-tertiary">
                  {role}
                </span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
