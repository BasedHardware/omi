'use client';

import { useMemo, useRef, useEffect, useState, useCallback } from 'react';
import { Tag, HelpCircle, Play, Pencil, Check, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TranscriptSegment } from '@/types/conversation';
import type { Person } from '@/types/user';

interface TranscriptViewProps {
  segments: TranscriptSegment[];
  userName?: string;
  conversationId?: string;
  people?: Person[];
  editable?: boolean;
  onSpeakerClick?: (segment: TranscriptSegment) => void;
  /**
   * Queue an edit to a single segment's text. Fire-and-forget: the parent shows
   * the change optimistically and persists it (serialized). When omitted, text
   * editing is disabled and only the speaker remains editable.
   */
  onSegmentTextChange?: (segmentId: string, text: string) => void;
  /** Id of the segment whose save is currently in flight (shows a spinner). */
  savingSegmentId?: string | null;
  /** When true, text editing is suppressed (e.g. while reprocessing). */
  editingDisabled?: boolean;
  /** Current audio playback time in seconds */
  currentTime?: number;
  /** Whether audio is available for this conversation */
  hasAudio?: boolean;
  /** Callback when user clicks on a segment to seek to that time */
  onSeekTo?: (time: number) => void;
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
  people?: Person[],
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
  return { name: `Speaker ${(segment.speaker_id ?? 0) + 1}`, isTagged: false };
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
    const speakerId = segment.speaker_id ?? null;
    if (speakerId !== currentSpeaker) {
      if (currentGroup.length > 0) {
        groups.push(currentGroup);
      }
      currentGroup = [segment];
      currentSpeaker = speakerId;
    } else {
      currentGroup.push(segment);
    }
  }

  if (currentGroup.length > 0) {
    groups.push(currentGroup);
  }

  return groups;
}

/**
 * Check if a time falls within a segment group's range
 */
function isActiveGroup(
  group: TranscriptSegment[],
  currentTime: number | undefined,
): boolean {
  if (currentTime === undefined) return false;
  const firstSegment = group[0];
  const lastSegment = group[group.length - 1];
  return currentTime >= firstSegment.start && currentTime <= lastSegment.end;
}

/**
 * Inline editor for a single transcript segment's text.
 *
 * The transcript is displayed as merged same-speaker blocks, but the backend
 * edits one segment at a time (keyed by `segment.id`). So in edit mode each
 * underlying segment gets its own field — the edit granularity matches the API.
 * Mirrors the `EditableTitle` interaction: Enter / blur saves, Escape cancels.
 */
function SegmentTextEditor({
  segment,
  onEnqueueSave,
  onExitEdit,
}: {
  segment: TranscriptSegment;
  onEnqueueSave: (segmentId: string, text: string) => void;
  onExitEdit: () => void;
}) {
  const [draft, setDraft] = useState(segment.text);
  // Guard so Enter/Done (which close the editor) don't also commit a second time
  // via the blur that firing focus-loss triggers as the field unmounts.
  const committedRef = useRef(false);

  const canEdit = Boolean(segment.id);

  // Queue the edit (if changed) and close. The parent persists it serially and
  // owns the saving/error UI, so the editor stays intentionally lightweight.
  const commit = useCallback(() => {
    if (committedRef.current) return;
    committedRef.current = true;
    const trimmed = draft.trim();
    if (segment.id && trimmed && trimmed !== segment.text) {
      onEnqueueSave(segment.id, trimmed);
    }
    onExitEdit();
  }, [draft, segment.id, segment.text, onEnqueueSave, onExitEdit]);

  const cancel = useCallback(() => {
    committedRef.current = true; // stop the blur handler from committing
    onExitEdit();
  }, [onExitEdit]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Enter commits & closes; Shift+Enter inserts a newline; Escape cancels.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      commit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancel();
    }
  };

  if (!canEdit) {
    // Segments without an id cannot be targeted by the edit API.
    return (
      <p
        className="text-text-primary leading-relaxed opacity-60"
        title="This segment can't be edited"
      >
        {segment.text}
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commit}
        rows={Math.min(6, Math.max(2, Math.ceil(draft.length / 60)))}
        className={cn(
          'w-full resize-y rounded-lg px-3 py-2 text-sm leading-relaxed',
          'bg-bg-secondary border border-bg-quaternary text-text-primary',
          'outline-none focus:ring-2 focus:ring-white/20',
        )}
      />
      <div className="text-xs text-text-quaternary">Enter to save · Esc to cancel</div>
    </div>
  );
}

export function TranscriptView({
  segments,
  userName,
  conversationId,
  people,
  editable = false,
  onSpeakerClick,
  onSegmentTextChange,
  savingSegmentId,
  editingDisabled = false,
  currentTime,
  hasAudio = false,
  onSeekTo,
}: TranscriptViewProps) {
  const groupedSegments = useMemo(() => groupSegmentsBySpeaker(segments), [segments]);
  const activeGroupRef = useRef<HTMLDivElement>(null);
  const [editingGroupIndex, setEditingGroupIndex] = useState<number | null>(null);

  const textEditable =
    editable &&
    Boolean(conversationId) &&
    Boolean(onSegmentTextChange) &&
    !editingDisabled;

  // Close any open editor if text editing gets disabled (e.g. reprocess starts).
  useEffect(() => {
    if (editingDisabled) setEditingGroupIndex(null);
  }, [editingDisabled]);

  // Auto-scroll to keep active segment in view during playback
  useEffect(() => {
    if (activeGroupRef.current && currentTime !== undefined) {
      activeGroupRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [currentTime]);

  // Find the active group index for highlighting
  const activeGroupIndex = useMemo(() => {
    if (currentTime === undefined) return -1;
    return groupedSegments.findIndex((group) => isActiveGroup(group, currentTime));
  }, [groupedSegments, currentTime]);

  if (!segments || segments.length === 0) {
    return (
      <div className="text-center py-8 text-text-tertiary">No transcript available</div>
    );
  }

  const handleSpeakerClick = (segment: TranscriptSegment) => {
    if (!editable || !conversationId || !onSpeakerClick) return;
    onSpeakerClick(segment);
  };

  return (
    <div className="space-y-4">
      {groupedSegments.map((group, groupIndex) => {
        const firstSegment = group[0];
        const lastSegment = group[group.length - 1];
        const { name: speakerName, isTagged } = getSpeakerName(
          firstSegment,
          userName,
          people,
        );
        const isUser = firstSegment.is_user;
        const combinedText = group.map((s) => s.text).join(' ');
        const speakerColorIndex = isUser
          ? 0
          : ((firstSegment.speaker_id ?? 0) % (SPEAKER_COLORS.length - 1)) + 1;
        const isActive = groupIndex === activeGroupIndex;
        const isEditingGroup = editingGroupIndex === groupIndex;
        const isSavingGroup =
          savingSegmentId != null && group.some((s) => s.id === savingSegmentId);

        return (
          <div
            key={groupIndex}
            ref={isActive ? activeGroupRef : undefined}
            className={cn(
              'group/segment rounded-xl p-4 transition-all duration-200',
              isUser
                ? 'bg-purple-primary/10 border border-purple-primary/20'
                : 'bg-bg-tertiary',
              // Active segment highlighting during audio playback
              isActive && 'ring-2 ring-purple-primary/50 bg-purple-primary/5',
            )}
          >
            {/* Speaker header */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {/* Avatar */}
                <div
                  className={cn(
                    'w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium',
                    SPEAKER_COLORS[speakerColorIndex],
                  )}
                >
                  {speakerName.charAt(0).toUpperCase()}
                </div>

                {/* Speaker name - clickable when editable */}
                {editable && conversationId && onSpeakerClick ? (
                  <button
                    onClick={() => handleSpeakerClick(firstSegment)}
                    className={cn(
                      'flex items-center gap-1.5 text-sm font-medium',
                      'hover:underline underline-offset-2',
                      isUser
                        ? 'text-purple-primary'
                        : isTagged
                          ? 'text-text-secondary'
                          : 'text-text-tertiary',
                    )}
                  >
                    <span>{speakerName}</span>
                    {!isTagged && <HelpCircle className="w-3.5 h-3.5 text-warning" />}
                    {!isUser && <Tag className="w-3 h-3 opacity-50" />}
                  </button>
                ) : (
                  <span
                    className={cn(
                      'text-sm font-medium',
                      isUser ? 'text-purple-primary' : 'text-text-secondary',
                    )}
                  >
                    {speakerName}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {/* Timestamp - clickable when audio is available */}
                {hasAudio && onSeekTo ? (
                  <button
                    onClick={() => onSeekTo(firstSegment.start)}
                    className={cn(
                      'flex items-center gap-1.5 text-xs',
                      'text-text-quaternary hover:text-purple-primary transition-colors',
                      'group',
                    )}
                    title="Click to play from here"
                  >
                    <Play className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    <span>
                      {formatTimestamp(firstSegment.start)} -{' '}
                      {formatTimestamp(lastSegment.end)}
                    </span>
                  </button>
                ) : (
                  <span className="text-xs text-text-quaternary">
                    {formatTimestamp(firstSegment.start)} -{' '}
                    {formatTimestamp(lastSegment.end)}
                  </span>
                )}

                {/* Per-segment saving indicator (this block's edit is in flight) */}
                {isSavingGroup && (
                  <span className="flex items-center gap-1 text-xs text-text-quaternary">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Saving…</span>
                  </span>
                )}

                {/* Edit transcript text toggle */}
                {textEditable &&
                  (isEditingGroup ? (
                    <button
                      onClick={() => setEditingGroupIndex(null)}
                      className={cn(
                        'flex items-center gap-1 text-xs font-medium',
                        'text-text-secondary hover:text-text-primary transition-colors',
                      )}
                      title="Done editing"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Done</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => setEditingGroupIndex(groupIndex)}
                      className={cn(
                        'p-1 rounded-md text-text-quaternary',
                        'opacity-0 group-hover/segment:opacity-100 focus:opacity-100',
                        'hover:text-text-primary hover:bg-bg-quaternary/50 transition-all',
                      )}
                      title="Edit transcript text"
                      aria-label="Edit transcript text"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  ))}
              </div>
            </div>

            {/* Transcript text */}
            {isEditingGroup && onSegmentTextChange ? (
              <div className="space-y-2">
                {group.map((segment, i) => (
                  <SegmentTextEditor
                    key={segment.id ?? `${groupIndex}-${i}`}
                    segment={segment}
                    onEnqueueSave={onSegmentTextChange}
                    onExitEdit={() => setEditingGroupIndex(null)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-text-primary leading-relaxed">{combinedText}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
