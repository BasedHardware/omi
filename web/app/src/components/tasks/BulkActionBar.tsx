'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Trash2, Clock, X, ChevronDown, Copy, Download, FileJson, FileText, FileCode, CheckSquare, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItem } from '@/types/conversation';

interface BulkActionBarProps {
  selectedCount: number;
  selectedItems?: ActionItem[];
  onComplete?: () => void;
  onDelete: () => void;
  onSnooze?: (days: number) => void;
  onClear: () => void;
  onCopy?: () => void;
  onExport?: (format: 'csv' | 'json' | 'markdown') => void;
  // Inline mode props
  inline?: boolean;
  onSelectAll?: () => void;
  onDone?: () => void;
  allSelected?: boolean;
  totalCount?: number;
  // Hide task-specific actions (for use in Memories, etc.)
  hideComplete?: boolean;
  hideSnooze?: boolean;
}

export function BulkActionBar({
  selectedCount,
  selectedItems,
  onComplete,
  onDelete,
  onSnooze,
  onClear,
  onCopy,
  onExport,
  inline = false,
  onSelectAll,
  onDone,
  allSelected = false,
  totalCount = 0,
  hideComplete = false,
  hideSnooze = false,
}: BulkActionBarProps) {
  const [showSnoozeMenu, setShowSnoozeMenu] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);

  // For inline mode, always show the bar (it's part of the page layout)
  // For floating mode, hide when nothing selected
  if (!inline && selectedCount === 0) return null;

  const content = (
    <>
      {/* Select All - only in inline mode */}
      {inline && onSelectAll && (
        <>
          <button
            onClick={onSelectAll}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm',
              'transition-colors',
              allSelected
                ? 'bg-purple-primary/10 text-purple-primary'
                : 'text-text-tertiary hover:text-text-primary hover:bg-bg-quaternary'
            )}
          >
            {allSelected ? (
              <CheckSquare className="w-4 h-4" />
            ) : (
              <Square className="w-4 h-4" />
            )}
            <span>Select All</span>
          </button>
          <div className="w-px h-6 bg-bg-quaternary" />
        </>
      )}

      {/* Selection count */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-text-primary">
          {selectedCount} selected
        </span>
        {!inline && (
          <button
            onClick={onClear}
            className="p-1 rounded hover:bg-bg-tertiary text-text-quaternary hover:text-text-secondary transition-colors"
            title="Clear selection"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Divider */}
      <div className="w-px h-6 bg-bg-tertiary" />

      {/* Actions */}
      <div className="flex items-center gap-2">
        {/* Snooze dropdown - hidden when hideSnooze is true */}
        {!hideSnooze && onSnooze && (
          <div className="relative">
            <button
              onClick={() => setShowSnoozeMenu(!showSnoozeMenu)}
              disabled={selectedCount === 0}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'bg-bg-tertiary hover:bg-bg-quaternary',
                'text-text-secondary text-sm',
                'transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <Clock className="w-4 h-4" />
              <span>Snooze</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            {/* Dropdown menu */}
            <AnimatePresence>
              {showSnoozeMenu && (
                <motion.div
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 5 }}
                  transition={{ duration: 0.15 }}
                  className={cn(
                    inline ? 'absolute top-full mt-2 left-0' : 'absolute bottom-full mb-2 left-0',
                    'bg-bg-secondary border border-bg-tertiary rounded-lg',
                    'shadow-lg shadow-black/20',
                    'py-1 min-w-[120px] z-50'
                  )}
                >
                  <button
                    onClick={() => {
                      onSnooze(0);
                      setShowSnoozeMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary"
                  >
                    Today
                  </button>
                  <button
                    onClick={() => {
                      onSnooze(1);
                      setShowSnoozeMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary"
                  >
                    Tomorrow
                  </button>
                  <button
                    onClick={() => {
                      onSnooze(7);
                      setShowSnoozeMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary"
                  >
                    Next week
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Complete button - hidden when hideComplete is true */}
        {!hideComplete && onComplete && (
          <button
            onClick={onComplete}
            disabled={selectedCount === 0}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-success/20 hover:bg-success/30',
              'text-success text-sm',
              'transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Check className="w-4 h-4" />
            <span>Complete</span>
          </button>
        )}

        {/* Delete button */}
        <button
          onClick={onDelete}
          disabled={selectedCount === 0}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
            'bg-error/20 hover:bg-error/30',
            'text-error text-sm',
            'transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete</span>
        </button>

        {/* Divider */}
        {(onCopy || onExport) && <div className="w-px h-6 bg-bg-tertiary" />}

        {/* Copy button */}
        {onCopy && (
          <button
            onClick={onCopy}
            disabled={selectedCount === 0}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-bg-tertiary hover:bg-bg-quaternary',
              'text-text-secondary text-sm',
              'transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            title="Copy to clipboard"
          >
            <Copy className="w-4 h-4" />
            <span>Copy</span>
          </button>
        )}

        {/* Export dropdown */}
        {onExport && (
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={selectedCount === 0}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'bg-bg-tertiary hover:bg-bg-quaternary',
                'text-text-secondary text-sm',
                'transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <Download className="w-4 h-4" />
              <span>Export</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            {/* Export dropdown menu */}
            <AnimatePresence>
              {showExportMenu && (
                <motion.div
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 5 }}
                  transition={{ duration: 0.15 }}
                  className={cn(
                    inline ? 'absolute top-full mt-2 right-0' : 'absolute bottom-full mb-2 right-0',
                    'bg-bg-secondary border border-bg-tertiary rounded-lg',
                    'shadow-lg shadow-black/20',
                    'py-1 min-w-[140px] z-50'
                  )}
                >
                  <button
                    onClick={() => {
                      onExport('csv');
                      setShowExportMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary flex items-center gap-2"
                  >
                    <FileText className="w-3.5 h-3.5" />
                    CSV
                  </button>
                  <button
                    onClick={() => {
                      onExport('json');
                      setShowExportMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary flex items-center gap-2"
                  >
                    <FileJson className="w-3.5 h-3.5" />
                    JSON
                  </button>
                  <button
                    onClick={() => {
                      onExport('markdown');
                      setShowExportMenu(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-sm text-text-secondary hover:bg-bg-tertiary flex items-center gap-2"
                  >
                    <FileCode className="w-3.5 h-3.5" />
                    Markdown
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Done button - only in inline mode */}
      {inline && onDone && (
        <>
          <div className="w-px h-6 bg-bg-tertiary ml-auto" />
          <button
            onClick={onDone}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-purple-primary/10 hover:bg-purple-primary/20',
              'text-purple-primary text-sm font-medium',
              'transition-colors'
            )}
          >
            Done
          </button>
        </>
      )}
    </>
  );

  // Inline mode - normal flow layout
  if (inline) {
    return (
      <motion.div
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: 'auto' }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.2 }}
        className={cn(
          'flex items-center gap-3 py-2 px-3 rounded-lg',
          'bg-bg-tertiary/50 border border-bg-quaternary'
        )}
      >
        {content}
      </motion.div>
    );
  }

  // Floating mode - fixed position at bottom
  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 100, opacity: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className={cn(
          'fixed bottom-4 left-1/2 -translate-x-1/2',
          'bg-bg-secondary border border-bg-tertiary',
          'rounded-xl shadow-lg shadow-black/30',
          'px-4 py-3',
          'flex items-center gap-4',
          'z-50'
        )}
      >
        {content}
      </motion.div>
    </AnimatePresence>
  );
}
