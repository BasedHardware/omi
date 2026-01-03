'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSearch: (query: string) => void;
  placeholder?: string;
  debounceMs?: number;
  className?: string;
}

export function SearchBar({
  value,
  onChange,
  onSearch,
  placeholder = 'Search conversations...',
  debounceMs = 300,
  className,
}: SearchBarProps) {
  const [isFocused, setIsFocused] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isMac, setIsMac] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Detect OS for keyboard shortcut display
  useEffect(() => {
    setIsMac(navigator.platform.toLowerCase().includes('mac'));
  }, []);

  // Handle input change with debounce
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value;
      onChange(newValue);

      // Clear previous debounce
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }

      // Set new debounce for search
      debounceRef.current = setTimeout(() => {
        onSearch(newValue);
      }, debounceMs);
    },
    [onChange, onSearch, debounceMs]
  );

  // Clear search
  const handleClear = useCallback(() => {
    onChange('');
    onSearch('');
    inputRef.current?.focus();
  }, [onChange, onSearch]);

  // Keyboard shortcut: Cmd+K or Ctrl+K to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
      // Escape to blur and clear if empty
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        if (value === '') {
          inputRef.current?.blur();
        } else {
          handleClear();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [value, handleClear]);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return (
    <div
      className={cn('relative', className)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg',
          'bg-bg-secondary border transition-all duration-150',
          isFocused
            ? 'border-purple-primary/40 ring-2 ring-purple-primary/20'
            : 'border-transparent hover:border-bg-quaternary'
        )}
      >
        {/* Search icon */}
        <Search
          className={cn(
            'w-4 h-4 flex-shrink-0 transition-colors',
            isFocused ? 'text-purple-primary' : 'text-text-quaternary'
          )}
        />

        {/* Input */}
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleChange}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder={placeholder}
          className={cn(
            'flex-1 bg-transparent text-sm text-text-primary',
            'placeholder:text-text-quaternary',
            'outline-none'
          )}
        />

        {/* Keyboard shortcut hint or clear button */}
        <AnimatePresence mode="wait">
          {value ? (
            <motion.button
              key="clear"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ duration: 0.1 }}
              onClick={handleClear}
              className={cn(
                'p-1 rounded-md',
                'text-text-quaternary hover:text-text-secondary',
                'hover:bg-bg-tertiary transition-colors'
              )}
              aria-label="Clear search"
            >
              <X className="w-3.5 h-3.5" />
            </motion.button>
          ) : (
            <motion.div
              key="shortcut"
              initial={{ opacity: 0 }}
              animate={{ opacity: isHovered || isFocused ? 1 : 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className={cn(
                'hidden sm:flex items-center gap-0.5',
                'px-1.5 py-0.5 rounded',
                'bg-bg-tertiary text-text-quaternary text-xs'
              )}
            >
              <kbd className="font-sans">{isMac ? '⌘' : 'Ctrl'}</kbd>
              <kbd className="font-sans">K</kbd>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
