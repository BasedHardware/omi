'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { updateConversationTitle } from '@/lib/api';

interface EditableTitleProps {
  conversationId: string;
  title: string;
  onTitleChange?: (newTitle: string) => void;
  className?: string;
}

export function EditableTitle({
  conversationId,
  title,
  onTitleChange,
  className,
}: EditableTitleProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedTitle, setEditedTitle] = useState(title);
  const [isSaving, setIsSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Update local state when title prop changes
  useEffect(() => {
    if (!isEditing) {
      setEditedTitle(title);
    }
  }, [title, isEditing]);

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSave = useCallback(async () => {
    const trimmedTitle = editedTitle.trim();

    // Don't save if empty or unchanged
    if (!trimmedTitle || trimmedTitle === title) {
      setEditedTitle(title);
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    try {
      await updateConversationTitle(conversationId, trimmedTitle);
      onTitleChange?.(trimmedTitle);
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to update title:', error);
      // Revert on error
      setEditedTitle(title);
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  }, [conversationId, editedTitle, title, onTitleChange]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      setEditedTitle(title);
      setIsEditing(false);
    }
  };

  const handleDoubleClick = () => {
    setIsEditing(true);
  };

  const handleBlur = () => {
    handleSave();
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={editedTitle}
        onChange={(e) => setEditedTitle(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        disabled={isSaving}
        className={cn(
          'w-full bg-transparent border-b-2 border-purple-primary',
          'outline-none text-text-primary',
          'disabled:opacity-50',
          className
        )}
        placeholder="Enter title..."
      />
    );
  }

  return (
    <h1
      onDoubleClick={handleDoubleClick}
      title="Double-click to edit"
      className={cn(
        'cursor-text select-none',
        'hover:bg-bg-tertiary/50 rounded-lg transition-colors',
        '-mx-2 px-2 py-1',
        className
      )}
    >
      {title || 'Untitled Conversation'}
    </h1>
  );
}
