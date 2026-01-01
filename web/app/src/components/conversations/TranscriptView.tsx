'use client';

import { cn } from '@/lib/utils';
import type { TranscriptSegment } from '@/types/conversation';

interface TranscriptViewProps {
  segments: TranscriptSegment[];
  userName?: string;
}

/**
 * Format seconds to MM:SS
 */
function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Get speaker display name
 */
function getSpeakerName(segment: TranscriptSegment, userName?: string): string {
  if (segment.speaker_name) {
    return segment.speaker_name;
  }
  if (segment.is_user) {
    return userName || 'You';
  }
  return `Speaker ${segment.speaker_id + 1}`;
}

/**
 * Group consecutive segments by speaker for cleaner display
 */
function groupSegmentsBySpeaker(segments: TranscriptSegment[]): TranscriptSegment[][] {
  const groups: TranscriptSegment[][] = [];
  let currentGroup: TranscriptSegment[] = [];
  let currentSpeaker: number | null = null;

  for (const segment of segments) {
    if (segment.speaker_id !== currentSpeaker) {
      if (currentGroup.length > 0) {
        groups.push(currentGroup);
      }
      currentGroup = [segment];
      currentSpeaker = segment.speaker_id;
    } else {
      currentGroup.push(segment);
    }
  }

  if (currentGroup.length > 0) {
    groups.push(currentGroup);
  }

  return groups;
}

export function TranscriptView({ segments, userName }: TranscriptViewProps) {
  if (!segments || segments.length === 0) {
    return (
      <div className="text-center py-8 text-text-tertiary">
        No transcript available
      </div>
    );
  }

  const groupedSegments = groupSegmentsBySpeaker(segments);

  return (
    <div className="space-y-4">
      {groupedSegments.map((group, groupIndex) => {
        const firstSegment = group[0];
        const lastSegment = group[group.length - 1];
        const speakerName = getSpeakerName(firstSegment, userName);
        const isUser = firstSegment.is_user;
        const combinedText = group.map(s => s.text).join(' ');

        return (
          <div
            key={groupIndex}
            className={cn(
              'rounded-xl p-4',
              isUser
                ? 'bg-purple-primary/10 border border-purple-primary/20'
                : 'bg-bg-tertiary'
            )}
          >
            {/* Speaker header */}
            <div className="flex items-center justify-between mb-2">
              <span
                className={cn(
                  'text-sm font-medium',
                  isUser ? 'text-purple-primary' : 'text-text-secondary'
                )}
              >
                {speakerName}
              </span>
              <span className="text-xs text-text-quaternary">
                {formatTimestamp(firstSegment.start)} - {formatTimestamp(lastSegment.end)}
              </span>
            </div>

            {/* Transcript text */}
            <p className="text-text-primary leading-relaxed">
              {combinedText}
            </p>
          </div>
        );
      })}
    </div>
  );
}
