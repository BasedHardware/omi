'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MoreVertical,
  Copy,
  FileText,
  RefreshCw,
  Trash2,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { deleteConversation, reprocessConversation } from '@/lib/api';
import type { Conversation, TranscriptSegment } from '@/types/conversation';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

interface ConversationActionsMenuProps {
  conversation: Conversation;
  onConversationUpdate?: (conversation: Conversation) => void;
  onDelete?: () => void;
  className?: string;
}

/**
 * Generate transcript text from segments
 */
function generateTranscript(segments: TranscriptSegment[]): string {
  if (!segments || segments.length === 0) return '';

  return segments
    .map((segment) => {
      const speaker = segment.is_user ? 'You' : `Speaker ${segment.speaker_id}`;
      return `${speaker}: ${segment.text}`;
    })
    .join('\n\n');
}

/**
 * Get summary content (prioritize app results, fallback to overview)
 */
function getSummaryContent(conversation: Conversation): string {
  if (conversation.apps_results?.length > 0 && conversation.apps_results[0].content?.trim()) {
    return conversation.apps_results[0].content.trim();
  }
  return conversation.structured.overview || '';
}

export function ConversationActionsMenu({
  conversation,
  onConversationUpdate,
  onDelete,
  className,
}: ConversationActionsMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copiedItem, setCopiedItem] = useState<'transcript' | 'summary' | null>(null);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setShowDeleteConfirm(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  const handleCopyTranscript = async () => {
    const transcript = generateTranscript(conversation.transcript_segments);
    if (!transcript) return;

    await navigator.clipboard.writeText(transcript);
    setCopiedItem('transcript');
    setTimeout(() => setCopiedItem(null), 2000);
  };

  const handleCopySummary = async () => {
    const summary = getSummaryContent(conversation);
    if (!summary) return;

    await navigator.clipboard.writeText(summary);
    setCopiedItem('summary');
    setTimeout(() => setCopiedItem(null), 2000);
  };

  const handleReprocess = async () => {
    if (isReprocessing) return;

    setIsReprocessing(true);
    try {
      const updated = await reprocessConversation(conversation.id);
      onConversationUpdate?.(updated);
      setIsOpen(false);
    } catch (error) {
      console.error('Failed to reprocess conversation:', error);
    } finally {
      setIsReprocessing(false);
    }
  };

  const handleDelete = async () => {
    if (isDeleting) return;

    setIsDeleting(true);
    try {
      await deleteConversation(conversation.id);
      MixpanelManager.track('Conversation Deleted', {
        conversation_id: conversation.id,
      });
      setIsOpen(false);
      onDelete?.();
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    } finally {
      setIsDeleting(false);
    }
  };

  const hasTranscript = conversation.transcript_segments?.length > 0;
  const hasSummary = Boolean(getSummaryContent(conversation));

  return (
    <div ref={menuRef} className={cn('relative', className)}>
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'p-2 rounded-lg transition-colors',
          'hover:bg-bg-tertiary text-text-secondary hover:text-text-primary',
          isOpen && 'bg-bg-tertiary text-text-primary'
        )}
        aria-label="Conversation actions"
      >
        <MoreVertical className="w-5 h-5" />
      </button>

      {/* Dropdown menu */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'absolute right-0 top-full mt-2 z-50',
              'min-w-[200px] py-2 rounded-xl',
              'bg-bg-secondary border border-bg-tertiary shadow-xl'
            )}
          >
            {/* Copy Transcript */}
            {hasTranscript && (
              <button
                onClick={handleCopyTranscript}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-2.5',
                  'text-sm text-text-secondary hover:text-text-primary',
                  'hover:bg-bg-tertiary transition-colors'
                )}
              >
                {copiedItem === 'transcript' ? (
                  <Check className="w-4 h-4 text-success" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
                <span>{copiedItem === 'transcript' ? 'Copied!' : 'Copy Transcript'}</span>
              </button>
            )}

            {/* Copy Summary */}
            {hasSummary && (
              <button
                onClick={handleCopySummary}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-2.5',
                  'text-sm text-text-secondary hover:text-text-primary',
                  'hover:bg-bg-tertiary transition-colors'
                )}
              >
                {copiedItem === 'summary' ? (
                  <Check className="w-4 h-4 text-success" />
                ) : (
                  <FileText className="w-4 h-4" />
                )}
                <span>{copiedItem === 'summary' ? 'Copied!' : 'Copy Summary'}</span>
              </button>
            )}

            {/* Divider */}
            {(hasTranscript || hasSummary) && (
              <div className="my-2 border-t border-bg-tertiary" />
            )}

            {/* Reprocess */}
            {!conversation.discarded && (
              <button
                onClick={handleReprocess}
                disabled={isReprocessing}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-2.5',
                  'text-sm text-text-secondary hover:text-text-primary',
                  'hover:bg-bg-tertiary transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                <RefreshCw className={cn('w-4 h-4', isReprocessing && 'animate-spin')} />
                <span>{isReprocessing ? 'Reprocessing...' : 'Reprocess Conversation'}</span>
              </button>
            )}

            {/* Divider before delete */}
            <div className="my-2 border-t border-bg-tertiary" />

            {/* Delete */}
            {showDeleteConfirm ? (
              <div className="px-4 py-2">
                <p className="text-sm text-text-secondary mb-2">Delete this conversation?</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    className="flex-1 px-3 py-1.5 text-sm rounded-lg bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={isDeleting}
                    className="flex-1 px-3 py-1.5 text-sm rounded-lg bg-error/20 text-error hover:bg-error/30 transition-colors disabled:opacity-50"
                  >
                    {isDeleting ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-2.5',
                  'text-sm text-error hover:bg-error/10',
                  'transition-colors'
                )}
              >
                <Trash2 className="w-4 h-4" />
                <span>Delete Conversation</span>
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
