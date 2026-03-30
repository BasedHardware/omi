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
                ? 'bg-brand/10 text-brand'
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
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-foreground">
          {selectedCount} selected
        </span>
        {!inline && (
          <button
            onClick={onClear}
            className="p-0.5 rounded hover:bg-accent text-muted-foreground transition-colors"
            title="Clear"
          >
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      <div className="w-px h-4 bg-border" />

      {/* Actions */}
      <div className="flex items-center gap-1">
        {!hideSnooze && onSnooze && (
          <div className="relative">
            <button
              onClick={() => setShowSnoozeMenu(!showSnoozeMenu)}
              disabled={selectedCount === 0}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-40"
            >
              <Clock className="w-3 h-3" />
              Snooze
              <ChevronDown className="w-2.5 h-2.5" />
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
                    'bg-bg-secondary border border-border rounded-lg',
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

        {!hideComplete && onComplete && (
          <button
            onClick={onComplete}
            disabled={selectedCount === 0}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-success hover:bg-success/10 transition-colors disabled:opacity-40"
          >
            <Check className="w-3 h-3" />
            Complete
          </button>
        )}

        <button
          onClick={onDelete}
          disabled={selectedCount === 0}
          className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-40"
        >
          <Trash2 className="w-3 h-3" />
          Delete
        </button>

        {(onCopy || onExport) && <div className="w-px h-4 bg-border" />}

        {onCopy && (
          <button
            onClick={onCopy}
            disabled={selectedCount === 0}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-40"
          >
            <Copy className="w-3 h-3" />
            Copy
          </button>
        )}

        {/* Export dropdown */}
        {onExport && (
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={selectedCount === 0}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-40"
            >
              <Download className="w-3 h-3" />
              Export
              <ChevronDown className="w-2.5 h-2.5" />
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
                    'bg-bg-secondary border border-border rounded-lg',
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

      {inline && onDone && (
        <>
          <div className="w-px h-4 bg-border ml-auto" />
          <button
            onClick={onDone}
            className="px-2 py-1 rounded-md text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
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
          'flex items-center gap-2 py-1.5 px-3 rounded-md',
          'bg-accent/50 border border-border/50'
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
          'bg-bg-secondary border border-border',
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
