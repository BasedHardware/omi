'use client';

import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, Eye, EyeOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Memory, MemoryVisibility } from '@/types/conversation';

interface MemoryQuickAddProps {
  onAdd: (content: string, visibility?: MemoryVisibility) => Promise<Memory | null>;
  disabled?: boolean;
}

export function MemoryQuickAdd({ onAdd, disabled = false }: MemoryQuickAddProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [content, setContent] = useState('');
  const [visibility, setVisibility] = useState<MemoryVisibility>('public');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isExpanded && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isExpanded]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!content.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const result = await onAdd(content.trim(), visibility);
      if (result) {
        setContent('');
        setVisibility('public');
        setIsExpanded(false);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  const handleCancel = () => {
    setContent('');
    setVisibility('public');
    setIsExpanded(false);
  };

  if (!isExpanded) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        disabled={disabled}
        className={cn(
          'flex items-center gap-2 w-full px-3 py-2.5',
          'rounded-lg border border-dashed border-bg-quaternary',
          'text-text-tertiary hover:text-text-secondary',
          'hover:border-purple-primary/50 hover:bg-bg-tertiary',
          'transition-all duration-150',
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      >
        <Plus className="w-4 h-4" />
        <span className="text-sm">Add a memory...</span>
      </button>
    );
  }

  return (
    <motion.form
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.15 }}
      onSubmit={handleSubmit}
      className={cn(
        'rounded-lg border border-purple-primary/50',
        'bg-bg-secondary p-3 space-y-3'
      )}
    >
      {/* Input */}
      <input
        ref={inputRef}
        type="text"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="What would you like to remember?"
        disabled={isSubmitting}
        className={cn(
          'w-full bg-transparent',
          'text-sm text-text-primary placeholder:text-text-quaternary',
          'outline-none'
        )}
      />

      {/* Actions row */}
      <div className="flex items-center justify-between gap-2">
        {/* Visibility toggle */}
        <button
          type="button"
          onClick={() => setVisibility(visibility === 'public' ? 'private' : 'public')}
          disabled={isSubmitting}
          className={cn(
            'flex items-center gap-1.5 px-2 py-1 rounded text-xs',
            'transition-colors',
            visibility === 'public'
              ? 'text-success hover:bg-success/10'
              : 'text-warning hover:bg-warning/10'
          )}
        >
          {visibility === 'public' ? (
            <>
              <Eye className="w-3 h-3" />
              Public
            </>
          ) : (
            <>
              <EyeOff className="w-3 h-3" />
              Private
            </>
          )}
        </button>

        {/* Buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCancel}
            disabled={isSubmitting}
            className={cn(
              'px-3 py-1 text-xs rounded',
              'text-text-tertiary hover:text-text-secondary',
              'transition-colors'
            )}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!content.trim() || isSubmitting}
            className={cn(
              'px-3 py-1 text-xs rounded',
              'bg-purple-primary hover:bg-purple-secondary',
              'text-white font-medium',
              'transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {isSubmitting ? 'Adding...' : 'Add Memory'}
          </button>
        </div>
      </div>

      {/* Hint */}
      <p className="text-[10px] text-text-quaternary">
        Press Enter to add, Escape to cancel
      </p>
    </motion.form>
  );
}
