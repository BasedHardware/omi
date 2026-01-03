'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Send, X, Eye, EyeOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Memory, MemoryVisibility } from '@/types/conversation';

interface MemoryQuickAddProps {
  onAdd: (content: string, visibility?: MemoryVisibility) => Promise<Memory | null>;
}

export function MemoryQuickAdd({ onAdd }: MemoryQuickAddProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [content, setContent] = useState('');
  const [visibility, setVisibility] = useState<MemoryVisibility>('public');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isExpanded && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isExpanded]);

  const handleSubmit = async () => {
    if (!content.trim() || isSubmitting) return;

    setIsSubmitting(true);
    const result = await onAdd(content.trim(), visibility);
    setIsSubmitting(false);

    if (result) {
      setContent('');
      setVisibility('public');
      setIsExpanded(false);
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
        className={cn(
          'w-full flex items-center gap-2 px-4 py-3',
          'rounded-xl border border-dashed border-bg-quaternary',
          'text-text-tertiary hover:text-text-secondary',
          'hover:border-purple-primary/30 hover:bg-bg-tertiary/50',
          'transition-all duration-150'
        )}
      >
        <Plus className="w-4 h-4" />
        <span className="text-sm">Add a memory...</span>
      </button>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'rounded-xl p-4',
        'bg-bg-tertiary border border-purple-primary/30',
        'shadow-lg shadow-purple-primary/5'
      )}
    >
      <textarea
        ref={inputRef}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
          } else if (e.key === 'Escape') {
            handleCancel();
          }
        }}
        placeholder="What would you like to remember?"
        className={cn(
          'w-full px-3 py-2 rounded-lg resize-none',
          'bg-bg-secondary border border-bg-quaternary',
          'text-sm text-text-primary',
          'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
          'placeholder:text-text-quaternary'
        )}
        rows={3}
      />

      <div className="flex items-center justify-between mt-3">
        {/* Visibility toggle */}
        <button
          onClick={() => setVisibility(visibility === 'public' ? 'private' : 'public')}
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm',
            'transition-colors',
            visibility === 'public'
              ? 'bg-success/10 text-success hover:bg-success/20'
              : 'bg-warning/10 text-warning hover:bg-warning/20'
          )}
        >
          {visibility === 'public' ? (
            <>
              <Eye className="w-3.5 h-3.5" />
              Public
            </>
          ) : (
            <>
              <EyeOff className="w-3.5 h-3.5" />
              Private
            </>
          )}
        </button>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleCancel}
            className={cn(
              'p-2 rounded-lg',
              'text-text-tertiary hover:text-text-primary',
              'hover:bg-bg-quaternary transition-colors'
            )}
          >
            <X className="w-4 h-4" />
          </button>
          <button
            onClick={handleSubmit}
            disabled={!content.trim() || isSubmitting}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'bg-purple-primary text-white text-sm font-medium',
              'hover:bg-purple-secondary transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Send className="w-3.5 h-3.5" />
            Add
          </button>
        </div>
      </div>
    </motion.div>
  );
}
