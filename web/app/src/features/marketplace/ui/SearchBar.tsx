'use client';

import { memo, useCallback, useState, useEffect, useMemo } from 'react';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import debounce from 'lodash/debounce';
import type { Plugin } from './types';
import { CompactPluginCard } from './plugin-card/CompactPluginCard';

interface SearchBarProps {
  className?: string;
  onSearching?: (searching: boolean) => void;
}

export const SearchBar = memo(function SearchBar({
  className,
  onSearching,
}: SearchBarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [searchResults, setSearchResults] = useState<Plugin[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSearch = useCallback(
    async (query: string) => {
      setSearchQuery(query);
      const searchContent = query.toLowerCase().trim();

      if (!searchContent) {
        setIsSearching(false);
        setSearchResults([]);
        setIsLoading(false);
        onSearching?.(false);
        return;
      }

      // Show searching state
      setIsSearching(true);
      setIsLoading(true);
      onSearching?.(true);

      try {
        // Call server-side search API
        const response = await fetch(`/api/apps/search?q=${encodeURIComponent(searchContent)}`);
        const data = await response.json();

        // Transform results to have capabilities as Set
        const transformedResults = (data.results || []).map((app: any) => ({
          ...app,
          capabilities: new Set(app.capabilities || []),
        }));

        setSearchResults(transformedResults);
      } catch (error) {
        console.error('Search failed:', error);
        setSearchResults([]);
      } finally {
        setIsLoading(false);
      }
    },
    [onSearching],
  );

  const debouncedSearch = useMemo(
    () => debounce((query: string) => handleSearch(query), 150),
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
    <div className="w-full">
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

      {/* Search Results */}
      {isSearching && (
        <div className="container mx-auto mt-8">
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-white">
              Search Results ({searchResults.length})
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {searchResults.map((plugin, index) => (
                <CompactPluginCard key={plugin.id} plugin={plugin} index={index + 1} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
