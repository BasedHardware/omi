'use client';

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Loader2, ChevronDown, ChevronUp, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PersonChip, YouChip, AddPersonChip } from './PersonChip';
import { usePeople } from '@/hooks/usePeople';
import { assignBulkTranscriptSegments } from '@/lib/api';
import type { TranscriptSegment } from '@/types/conversation';
import type { Person } from '@/types/user';

interface SpeakerTagSheetProps {
  isOpen: boolean;
  onClose: () => void;
  conversationId: string;
  segment: TranscriptSegment;
  allSegments: TranscriptSegment[];
  onAssignComplete?: (segmentIds: string[], personId: string | null, isUser: boolean) => void;
  onManagePeople?: () => void;
}

/**
 * Format seconds to HH:MM:SS or MM:SS
 */
function formatTimestamp(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Bottom sheet for tagging speakers in transcript segments
 * Slides up from the bottom within the detail panel area
 */
export function SpeakerTagSheet({
  isOpen,
  onClose,
  conversationId,
  segment,
  allSegments,
  onAssignComplete,
  onManagePeople,
}: SpeakerTagSheetProps) {
  const { people, loading: loadingPeople, addPerson } = usePeople();
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null);
  const [isYouSelected, setIsYouSelected] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAddPerson, setShowAddPerson] = useState(false);
  const [newPersonName, setNewPersonName] = useState('');
  const [creatingPerson, setCreatingPerson] = useState(false);

  // Bulk tagging state
  const [tagOtherSegments, setTagOtherSegments] = useState(false);
  const [selectedSegmentIds, setSelectedSegmentIds] = useState<Set<string>>(new Set());

  // Get other untagged segments from the same speaker
  const otherUntaggedSegments = useMemo(() => {
    if (!segment.id) return [];
    return allSegments.filter(
      (s) =>
        s.id !== segment.id &&
        s.speaker_id === segment.speaker_id &&
        !s.is_user &&
        !s.person_id
    );
  }, [segment, allSegments]);

  // Sort people by relevance (frequency in transcript, then alphabetically)
  const sortedPeople = useMemo(() => {
    // Count how often each person appears in the transcript
    const personCounts = new Map<string, number>();
    for (const s of allSegments) {
      if (s.person_id) {
        personCounts.set(s.person_id, (personCounts.get(s.person_id) || 0) + 1);
      }
    }

    return [...people].sort((a, b) => {
      // Current segment's person comes first
      if (segment.person_id === a.id) return -1;
      if (segment.person_id === b.id) return 1;

      // Then by frequency
      const countA = personCounts.get(a.id) || 0;
      const countB = personCounts.get(b.id) || 0;
      if (countA !== countB) return countB - countA;

      // Then alphabetically
      return a.name.localeCompare(b.name);
    });
  }, [people, allSegments, segment.person_id]);

  // Reset state when sheet opens
  useEffect(() => {
    if (isOpen) {
      setSelectedPersonId(segment.person_id || null);
      setIsYouSelected(segment.is_user);
      setError(null);
      setShowAddPerson(false);
      setNewPersonName('');
      setTagOtherSegments(false);
      setSelectedSegmentIds(new Set());
    }
  }, [isOpen, segment]);

  // Initialize selected segments when expanding bulk tagging
  useEffect(() => {
    if (tagOtherSegments && selectedSegmentIds.size === 0) {
      // Select all by default
      setSelectedSegmentIds(new Set(otherUntaggedSegments.map((s) => s.id!).filter(Boolean)));
    }
  }, [tagOtherSegments, otherUntaggedSegments, selectedSegmentIds.size]);

  const handleSelectPerson = (person: Person) => {
    if (selectedPersonId === person.id) {
      setSelectedPersonId(null);
    } else {
      setSelectedPersonId(person.id);
      setIsYouSelected(false);
    }
  };

  const handleSelectYou = () => {
    if (isYouSelected) {
      setIsYouSelected(false);
    } else {
      setIsYouSelected(true);
      setSelectedPersonId(null);
    }
  };

  const handleCreatePerson = async () => {
    if (!newPersonName.trim() || creatingPerson) return;

    // Validate: check for duplicates
    const normalizedName = newPersonName.trim().toLowerCase();
    if (people.some((p) => p.name.toLowerCase() === normalizedName)) {
      setError('A person with this name already exists');
      return;
    }

    setCreatingPerson(true);
    setError(null);

    try {
      const newPerson = await addPerson(newPersonName.trim());
      if (newPerson) {
        setSelectedPersonId(newPerson.id);
        setIsYouSelected(false);
        setShowAddPerson(false);
        setNewPersonName('');
      } else {
        setError('Failed to create person');
      }
    } finally {
      setCreatingPerson(false);
    }
  };

  const handleToggleSegment = (segmentId: string) => {
    setSelectedSegmentIds((prev) => {
      const next = new Set(prev);
      if (next.has(segmentId)) {
        next.delete(segmentId);
      } else {
        next.add(segmentId);
      }
      return next;
    });
  };

  const handleSave = async () => {
    if (!selectedPersonId && !isYouSelected) return;
    if (!segment.id) {
      setError('Segment has no ID');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      // Collect all segment IDs to update
      const segmentIds = [segment.id];
      if (tagOtherSegments) {
        segmentIds.push(...Array.from(selectedSegmentIds));
      }

      await assignBulkTranscriptSegments(conversationId, segmentIds, {
        isUser: isYouSelected,
        personId: isYouSelected ? null : selectedPersonId,
      });

      onAssignComplete?.(segmentIds, isYouSelected ? null : selectedPersonId, isYouSelected);
      onClose();
    } catch (err) {
      console.error('Failed to assign speaker:', err);
      setError('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const selectedCount = tagOtherSegments ? selectedSegmentIds.size : 0;
  const totalUntagged = otherUntaggedSegments.length;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop - only covers the panel area */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/40 z-40 rounded-xl"
          />

          {/* Bottom Sheet - slides up from bottom within panel */}
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={cn(
              'absolute bottom-0 left-0 right-0 z-50',
              'bg-bg-secondary rounded-t-2xl',
              'max-h-[80%] overflow-hidden flex flex-col',
              'shadow-xl border-t border-bg-tertiary'
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-bg-tertiary">
              <div className="flex-1 min-w-0">
                <h2 className="text-lg font-semibold text-text-primary">
                  Tag Speaker {segment.speaker_id + 1}
                </h2>
                <p className="text-sm text-text-tertiary truncate mt-0.5">
                  "{segment.text.slice(0, 50)}..."
                </p>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
              >
                <X className="w-5 h-5 text-text-tertiary" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* Error */}
              {error && (
                <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/20 text-error text-sm">
                  {error}
                </div>
              )}

              {/* Add Person Form */}
              {showAddPerson && (
                <div className="mb-4 p-3 rounded-lg bg-bg-tertiary border border-bg-quaternary">
                  <p className="text-sm font-medium text-text-primary mb-2">Add New Person</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newPersonName}
                      onChange={(e) => setNewPersonName(e.target.value)}
                      placeholder="Enter name..."
                      autoFocus
                      className={cn(
                        'flex-1 px-3 py-2 rounded-lg',
                        'bg-bg-secondary border border-bg-quaternary',
                        'text-sm text-text-primary placeholder:text-text-quaternary',
                        'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                      )}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleCreatePerson();
                        if (e.key === 'Escape') setShowAddPerson(false);
                      }}
                    />
                    <button
                      onClick={handleCreatePerson}
                      disabled={!newPersonName.trim() || creatingPerson}
                      className={cn(
                        'px-4 py-2 rounded-lg text-sm font-medium',
                        'bg-purple-primary hover:bg-purple-secondary text-white',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'transition-colors'
                      )}
                    >
                      {creatingPerson ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Add'}
                    </button>
                    <button
                      onClick={() => {
                        setShowAddPerson(false);
                        setNewPersonName('');
                      }}
                      className="px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-quaternary transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Person Selection */}
              <div className="mb-4">
                <p className="text-sm font-medium text-text-secondary mb-3">Select Person</p>
                {loadingPeople ? (
                  <div className="flex items-center gap-2 text-text-tertiary">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="text-sm">Loading people...</span>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    <YouChip selected={isYouSelected} onClick={handleSelectYou} />
                    {sortedPeople.map((person, index) => (
                      <PersonChip
                        key={person.id}
                        person={person}
                        selected={selectedPersonId === person.id}
                        onClick={() => handleSelectPerson(person)}
                        colorIndex={index}
                      />
                    ))}
                    {!showAddPerson && (
                      <AddPersonChip onClick={() => setShowAddPerson(true)} />
                    )}
                  </div>
                )}
              </div>

              {/* Bulk Tagging Section */}
              {otherUntaggedSegments.length > 0 && (
                <div className="border-t border-bg-tertiary pt-4">
                  {/* Toggle Header */}
                  <button
                    onClick={() => setTagOtherSegments(!tagOtherSegments)}
                    className={cn(
                      'w-full flex items-center justify-between p-3 rounded-lg',
                      'bg-bg-tertiary hover:bg-bg-quaternary transition-colors',
                      'text-left'
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={tagOtherSegments}
                        onChange={() => {}}
                        className="w-4 h-4 rounded border-bg-quaternary text-purple-primary focus:ring-purple-primary"
                      />
                      <div>
                        <p className="text-sm font-medium text-text-primary">
                          Tag other segments from this speaker
                        </p>
                        <p className="text-xs text-text-tertiary">
                          {tagOtherSegments
                            ? `${selectedCount}/${totalUntagged} selected`
                            : `${totalUntagged} untagged segment${totalUntagged !== 1 ? 's' : ''}`}
                        </p>
                      </div>
                    </div>
                    {tagOtherSegments ? (
                      <ChevronUp className="w-4 h-4 text-text-tertiary" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-text-tertiary" />
                    )}
                  </button>

                  {/* Segment List */}
                  {tagOtherSegments && (
                    <div className="mt-3 max-h-40 overflow-y-auto space-y-2">
                      {otherUntaggedSegments.map((s) => (
                        <label
                          key={s.id}
                          className={cn(
                            'flex items-start gap-3 p-3 rounded-lg cursor-pointer',
                            'bg-bg-tertiary hover:bg-bg-quaternary transition-colors',
                            selectedSegmentIds.has(s.id!) && 'ring-1 ring-purple-primary/50'
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={selectedSegmentIds.has(s.id!)}
                            onChange={() => handleToggleSegment(s.id!)}
                            className="mt-0.5 w-4 h-4 rounded border-bg-quaternary text-purple-primary focus:ring-purple-primary"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-text-primary line-clamp-2">{s.text}</p>
                            <p className="text-xs text-text-quaternary mt-1">
                              [{formatTimestamp(s.start)} - {formatTimestamp(s.end)}]
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Manage People Link - always visible */}
              {onManagePeople && (
                <div className={cn(
                  otherUntaggedSegments.length > 0 ? 'mt-4' : 'border-t border-bg-tertiary pt-4'
                )}>
                  <button
                    onClick={onManagePeople}
                    className={cn(
                      'flex items-center gap-2 text-sm text-text-tertiary',
                      'hover:text-text-secondary transition-colors'
                    )}
                  >
                    <Settings className="w-4 h-4" />
                    <span>Manage People</span>
                  </button>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-bg-tertiary">
              <button
                onClick={handleSave}
                disabled={(!selectedPersonId && !isYouSelected) || saving}
                className={cn(
                  'w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl',
                  'text-sm font-medium transition-all duration-150',
                  'bg-purple-primary hover:bg-purple-secondary text-white',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                {saving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <span>
                    Save{tagOtherSegments && selectedCount > 0 ? ` (${selectedCount + 1} segments)` : ''}
                  </span>
                )}
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
