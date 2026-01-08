'use client';

import { useEffect, useState, useCallback } from 'react';

interface UseTaskKeyboardShortcutsProps {
  enabled: boolean;
  selectedIds: Set<string>;
  focusedIndex: number;
  totalItems: number;

  // Actions
  onSetDueToday: (ids: string[]) => void;
  onSetDueTomorrow: (ids: string[]) => void;
  onDelete: (ids: string[]) => void;
  onToggleComplete: (ids: string[]) => void;
  onStartEdit: (id: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onNavigate: (direction: 'up' | 'down') => void;
  onToggleSelectFocused: () => void;
}

interface UseTaskKeyboardShortcutsReturn {
  isMac: boolean;
}

export function useTaskKeyboardShortcuts({
  enabled,
  selectedIds,
  focusedIndex,
  totalItems,
  onSetDueToday,
  onSetDueTomorrow,
  onDelete,
  onToggleComplete,
  onStartEdit,
  onSelectAll,
  onDeselectAll,
  onNavigate,
  onToggleSelectFocused,
}: UseTaskKeyboardShortcutsProps): UseTaskKeyboardShortcutsReturn {
  const [isMac, setIsMac] = useState(true);

  // Detect OS on mount
  useEffect(() => {
    setIsMac(
      typeof navigator !== 'undefined' &&
        navigator.platform.toLowerCase().includes('mac')
    );
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;

      // Don't trigger if user is typing in an input
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        // Allow Escape to work even in inputs
        if (e.key !== 'Escape') {
          return;
        }
      }

      const modKey = isMac ? e.metaKey : e.ctrlKey;
      const ids = Array.from(selectedIds);

      switch (e.key.toLowerCase()) {
        case 't':
          // Set due to today
          if (!modKey && ids.length > 0) {
            e.preventDefault();
            onSetDueToday(ids);
          }
          break;

        case 'n':
          // Set due to tomorrow
          if (!modKey && ids.length > 0) {
            e.preventDefault();
            onSetDueTomorrow(ids);
          }
          break;

        case 'd':
          // Delete selected
          if (!modKey && ids.length > 0) {
            e.preventDefault();
            onDelete(ids);
          }
          break;

        case 'e':
          // Edit description (single selection only)
          if (!modKey && ids.length === 1) {
            e.preventDefault();
            onStartEdit(ids[0]);
          }
          break;

        case 'a':
          // Select all
          if (modKey) {
            e.preventDefault();
            onSelectAll();
          }
          break;

        case 'enter':
          // Toggle complete
          if (!modKey && ids.length > 0) {
            e.preventDefault();
            onToggleComplete(ids);
          }
          break;

        case 'escape':
          // Deselect all
          e.preventDefault();
          onDeselectAll();
          break;

        case 'arrowup':
          // Navigate up
          if (!modKey && totalItems > 0) {
            e.preventDefault();
            onNavigate('up');
          }
          break;

        case 'arrowdown':
          // Navigate down
          if (!modKey && totalItems > 0) {
            e.preventDefault();
            onNavigate('down');
          }
          break;

        case ' ':
          // Toggle select focused item
          if (!modKey && focusedIndex >= 0) {
            e.preventDefault();
            onToggleSelectFocused();
          }
          break;
      }
    },
    [
      enabled,
      isMac,
      selectedIds,
      focusedIndex,
      totalItems,
      onSetDueToday,
      onSetDueTomorrow,
      onDelete,
      onToggleComplete,
      onStartEdit,
      onSelectAll,
      onDeselectAll,
      onNavigate,
      onToggleSelectFocused,
    ]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return { isMac };
}

// Keyboard shortcut definitions for help display
export const KEYBOARD_SHORTCUTS = [
  { key: 't', description: 'Set due today', requiresSelection: true },
  { key: 'n', description: 'Set due tomorrow', requiresSelection: true },
  { key: 'd', description: 'Delete selected', requiresSelection: true },
  { key: 'e', description: 'Edit description', requiresSelection: true, singleOnly: true },
  { key: '⌘/Ctrl + A', description: 'Select all', requiresSelection: false },
  { key: 'Enter', description: 'Toggle complete', requiresSelection: true },
  { key: 'Escape', description: 'Deselect all', requiresSelection: false },
  { key: '↑ / ↓', description: 'Navigate', requiresSelection: false },
  { key: 'Space', description: 'Toggle select', requiresSelection: false },
] as const;
