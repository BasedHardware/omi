'use client';

import { Search, X } from 'lucide-react';
import { useCallback, useState, useEffect } from 'react';
import { cn } from '@/src/lib/utils';
import debounce from 'lodash/debounce';

interface SearchBarProps {
  className?: string;
}

export function SearchBar({ className }: SearchBarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
    const searchContent = query.toLowerCase().trim();
    const cards = document.querySelectorAll('[data-plugin-card]');
    cards.forEach((card) => {
      const content = card.getAttribute('data-search-content')?.toLowerCase() || '';
      const categories = card.getAttribute('data-categories')?.toLowerCase() || '';
      const capabilities = card.getAttribute('data-capabilities')?.toLowerCase() || '';
      if (
        searchContent === '' ||
        content.includes(searchContent) ||
        categories.includes(searchContent) ||
        capabilities.includes(searchContent)
      ) {
        card.classList.remove('search-hidden');
      } else {
        card.classList.add('search-hidden');
      }
    });

    document.querySelectorAll('section').forEach((section) => {
      const visibleCards = section.querySelectorAll(
        '[data-plugin-card]:not(.search-hidden)',
      );
      if (visibleCards.length === 0) {
        section.classList.add('search-hidden');
      } else {
        section.classList.remove('search-hidden');
      }
    });
  }, []);

  const debouncedSearch = useCallback(
    debounce((query: string) => handleSearch(query), 150),
    [handleSearch],
  );

  const clearSearch = useCallback(() => {
    setSearchQuery('');
    handleSearch('');
  }, [handleSearch]);

  useEffect(() => {
    return () => {
      debouncedSearch.cancel();
    };
  }, [debouncedSearch]);

  return (
    <div className={cn('relative mx-auto w-full max-w-2xl', className)}>
      <div className="group relative">
        <Search
          className={cn(
            'absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 transition-colors',
            isFocused || searchQuery
              ? 'text-[#6C8EEF]'
              : 'text-gray-400 group-hover:text-[#6C8EEF]',
          )}
        />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            debouncedSearch(e.target.value);
          }}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder="Search apps, categories, or capabilities..."
          className="h-12 w-full rounded-full bg-[#1A1F2E] pl-11 pr-11 text-sm text-white placeholder-gray-400 outline-none ring-1 ring-white/5 transition-all hover:ring-white/10 focus:bg-[#242938] focus:ring-[#6C8EEF]/50"
        />
        {searchQuery && (
          <button
            onClick={clearSearch}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
} 