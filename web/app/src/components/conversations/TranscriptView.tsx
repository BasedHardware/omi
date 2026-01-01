'use client';

import { useState, useMemo } from 'react';
import { Tag, HelpCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SpeakerTagSheet } from './SpeakerTagSheet';
import { ManagePeopleModal } from './ManagePeopleModal';
import type { TranscriptSegment, Conversation } from '@/types/conversation';
import type { Person } from '@/types/user';

interface TranscriptViewProps {
  segments: TranscriptSegment[];
  userName?: string;
  conversationId?: string;
  people?: Person[];
  editable?: boolean;
  onSegmentsUpdate?: (segments: TranscriptSegment[]) => void;
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
function getSpeakerName(
  segment: TranscriptSegment,
  userName?: string,
  people?: Person[]
): { name: string; isTagged: boolean } {
  // Check if has person_id and find the person
  if (segment.person_id && people) {
    const person = people.find((p) => p.id === segment.person_id);
    if (person) {
      return { name: person.name, isTagged: true };
    }
  }

  // Check if segment has a pre-populated speaker_name
  if (segment.speaker_name) {
    return { name: segment.speaker_name, isTagged: true };
  }

  // Check if it's the user
  if (segment.is_user) {
    return { name: userName || 'You', isTagged: true };
  }

  // Default: untagged speaker
  return { name: `Speaker ${segment.speaker_id + 1}`, isTagged: false };
}

// Speaker avatar colors matching mobile app
const SPEAKER_COLORS = [
  'bg-purple-primary/30 text-purple-primary', // user
  'bg-amber-700/30 text-amber-300',
  'bg-blue-900/30 text-blue-300',
  'bg-emerald-800/30 text-emerald-300',
  'bg-rose-900/30 text-rose-300',
  'bg-cyan-700/30 text-cyan-300',
  'bg-lime-800/30 text-lime-300',
  'bg-purple-800/30 text-purple-300',
  'bg-orange-800/30 text-orange-300',
];

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

export function TranscriptView({
  segments,
  userName,
  conversationId,
  people,
  editable = false,
  onSegmentsUpdate,
}: TranscriptViewProps) {
  const [selectedSegment, setSelectedSegment] = useState<TranscriptSegment | null>(null);
  const [showTagSheet, setShowTagSheet] = useState(false);
  const [showManagePeople, setShowManagePeople] = useState(false);

  const groupedSegments = useMemo(() => groupSegmentsBySpeaker(segments), [segments]);

  if (!segments || segments.length === 0) {
    return (
      <div className="text-center py-8 text-text-tertiary">
        No transcript available
      </div>
    );
  }

  const handleSpeakerClick = (segment: TranscriptSegment) => {
    if (!editable || !conversationId) return;
    setSelectedSegment(segment);
    setShowTagSheet(true);
  };

  const handleAssignComplete = (
    segmentIds: string[],
    personId: string | null,
    isUser: boolean
  ) => {
    if (!onSegmentsUpdate) return;

    // Update local segments state
    const updatedSegments = segments.map((seg) => {
      if (seg.id && segmentIds.includes(seg.id)) {
        return {
          ...seg,
          is_user: isUser,
          person_id: isUser ? null : personId,
        };
      }
      return seg;
    });

    onSegmentsUpdate(updatedSegments);
  };

  return (
    <>
      <div className="space-y-4">
        {groupedSegments.map((group, groupIndex) => {
          const firstSegment = group[0];
          const lastSegment = group[group.length - 1];
          const { name: speakerName, isTagged } = getSpeakerName(firstSegment, userName, people);
          const isUser = firstSegment.is_user;
          const combinedText = group.map((s) => s.text).join(' ');
          const speakerColorIndex = isUser ? 0 : (firstSegment.speaker_id % (SPEAKER_COLORS.length - 1)) + 1;

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
                <div className="flex items-center gap-2">
                  {/* Avatar */}
                  <div
                    className={cn(
                      'w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium',
                      SPEAKER_COLORS[speakerColorIndex]
                    )}
                  >
                    {speakerName.charAt(0).toUpperCase()}
                  </div>

                  {/* Speaker name - clickable when editable */}
                  {editable && conversationId ? (
                    <button
                      onClick={() => handleSpeakerClick(firstSegment)}
                      className={cn(
                        'flex items-center gap-1.5 text-sm font-medium',
                        'hover:underline underline-offset-2',
                        isUser
                          ? 'text-purple-primary'
                          : isTagged
                          ? 'text-text-secondary'
                          : 'text-text-tertiary'
                      )}
                    >
                      <span>{speakerName}</span>
                      {!isTagged && (
                        <HelpCircle className="w-3.5 h-3.5 text-warning" />
                      )}
                      {!isUser && (
                        <Tag className="w-3 h-3 opacity-50" />
                      )}
                    </button>
                  ) : (
                    <span
                      className={cn(
                        'text-sm font-medium',
                        isUser ? 'text-purple-primary' : 'text-text-secondary'
                      )}
                    >
                      {speakerName}
                    </span>
                  )}
                </div>

                <span className="text-xs text-text-quaternary">
                  {formatTimestamp(firstSegment.start)} - {formatTimestamp(lastSegment.end)}
                </span>
              </div>

              {/* Transcript text */}
              <p className="text-text-primary leading-relaxed">{combinedText}</p>
            </div>
          );
        })}
      </div>

      {/* Speaker Tag Sheet */}
      {selectedSegment && conversationId && (
        <SpeakerTagSheet
          isOpen={showTagSheet}
          onClose={() => {
            setShowTagSheet(false);
            setSelectedSegment(null);
          }}
          conversationId={conversationId}
          segment={selectedSegment}
          allSegments={segments}
          onAssignComplete={handleAssignComplete}
          onManagePeople={() => {
            setShowTagSheet(false);
            setShowManagePeople(true);
          }}
        />
      )}

      {/* Manage People Modal */}
      <ManagePeopleModal
        isOpen={showManagePeople}
        onClose={() => {
          setShowManagePeople(false);
          // Reopen tag sheet if we have a selected segment
          if (selectedSegment) {
            setShowTagSheet(true);
          }
        }}
      />
    </>
  );
}
