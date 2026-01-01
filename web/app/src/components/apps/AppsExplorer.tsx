'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { Search, SlidersHorizontal, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  getAppsGrouped,
  searchApps,
  getPopularApps,
  getAppCategories,
  getAppCapabilities,
} from '@/lib/api';
import type {
  App,
  AppCategory,
  AppCapability,
  AppGroup,
  AppsFilters,
  SortOption,
} from '@/types/apps';
import { AppCard } from './AppCard';
import { AppGridSection } from './AppGridSection';
import { FilterSheet } from './FilterSheet';

type Tab = 'explore' | 'installed';

export function AppsExplorer() {
  const [activeTab, setActiveTab] = useState<Tab>('explore');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Data
  const [appGroups, setAppGroups] = useState<AppGroup[]>([]);
  const [popularApps, setPopularApps] = useState<App[]>([]);
  const [searchResults, setSearchResults] = useState<App[]>([]);
  const [installedApps, setInstalledApps] = useState<App[]>([]);
  const [categories, setCategories] = useState<AppCategory[]>([]);
  const [capabilities, setCapabilities] = useState<AppCapability[]>([]);

  // Filters
  const [filters, setFilters] = useState<AppsFilters>({});
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.category) count++;
    if (filters.capability) count++;
    if (filters.rating) count++;
    if (filters.sort && filters.sort !== 'installs_desc') count++;
    return count;
  }, [filters]);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Load initial data
  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const [groupedData, popular, cats, caps] = await Promise.all([
          getAppsGrouped(),
          getPopularApps(),
          getAppCategories(),
          getAppCapabilities(),
        ]);
        setAppGroups(groupedData.groups || []);
        setPopularApps(popular || []);
        setCategories(cats || []);
        setCapabilities(caps || []);
      } catch (err) {
        console.error('Failed to load apps:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  // Search or filter apps
  useEffect(() => {
    async function performSearch() {
      const hasFilters = filters.category || filters.capability || filters.rating || filters.sort;
      const hasQuery = debouncedQuery.trim().length > 0;

      if (!hasFilters && !hasQuery) {
        setSearchResults([]);
        return;
      }

      setIsSearching(true);
      try {
        const response = await searchApps({
          q: debouncedQuery || undefined,
          category: filters.category,
          capability: filters.capability,
          rating: filters.rating,
          sort: filters.sort,
          installed_apps: activeTab === 'installed' ? true : undefined,
          limit: 50,
        });
        setSearchResults(response.data || []);
      } catch (err) {
        console.error('Search failed:', err);
      } finally {
        setIsSearching(false);
      }
    }
    performSearch();
  }, [debouncedQuery, filters, activeTab]);

  // Load installed apps when switching to installed tab
  useEffect(() => {
    async function loadInstalled() {
      if (activeTab !== 'installed') return;

      setIsLoading(true);
      try {
        const response = await searchApps({ installed_apps: true, limit: 100 });
        setInstalledApps(response.data || []);
      } catch (err) {
        console.error('Failed to load installed apps:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadInstalled();
  }, [activeTab]);

  const handleFilterChange = useCallback((newFilters: AppsFilters) => {
    setFilters(newFilters);
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({});
    setSearchQuery('');
  }, []);

  // Refresh app list after enable/disable
  const handleAppUpdate = useCallback(async () => {
    if (activeTab === 'installed') {
      const response = await searchApps({ installed_apps: true, limit: 100 });
      setInstalledApps(response.data || []);
    }
    // Refresh groups to update enabled state
    const groupedData = await getAppsGrouped();
    setAppGroups(groupedData.groups || []);
  }, [activeTab]);

  const isShowingSearchResults = debouncedQuery.trim().length > 0 || activeFilterCount > 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-bg-tertiary bg-bg-secondary">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <h1 className="text-2xl font-bold text-text-primary mb-4">Apps</h1>

          {/* Tabs */}
          <div className="flex gap-1 mb-4">
            <button
              onClick={() => setActiveTab('explore')}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                activeTab === 'explore'
                  ? 'bg-purple-primary text-white'
                  : 'text-text-secondary hover:bg-bg-tertiary'
              )}
            >
              Explore
            </button>
            <button
              onClick={() => setActiveTab('installed')}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                activeTab === 'installed'
                  ? 'bg-purple-primary text-white'
                  : 'text-text-secondary hover:bg-bg-tertiary'
              )}
            >
              Installed
            </button>
          </div>

          {/* Search and Filter */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-text-quaternary" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search apps..."
                className={cn(
                  'w-full pl-10 pr-10 py-2.5 rounded-xl',
                  'bg-bg-tertiary border border-bg-quaternary',
                  'text-text-primary placeholder:text-text-quaternary',
                  'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                  'transition-all'
                )}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-bg-quaternary"
                >
                  <X className="w-4 h-4 text-text-tertiary" />
                </button>
              )}
            </div>
            <button
              onClick={() => setShowFilters(true)}
              className={cn(
                'px-4 py-2.5 rounded-xl flex items-center gap-2',
                'border transition-colors',
                activeFilterCount > 0
                  ? 'bg-purple-primary/10 border-purple-primary text-purple-primary'
                  : 'bg-bg-tertiary border-bg-quaternary text-text-secondary hover:bg-bg-quaternary'
              )}
            >
              <SlidersHorizontal className="w-5 h-5" />
              <span className="hidden sm:inline">Filters</span>
              {activeFilterCount > 0 && (
                <span className="w-5 h-5 rounded-full bg-purple-primary text-white text-xs flex items-center justify-center">
                  {activeFilterCount}
                </span>
              )}
            </button>
          </div>

          {/* Active filters display */}
          {activeFilterCount > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {filters.category && (
                <FilterChip
                  label={categories.find(c => c.id === filters.category)?.title || filters.category}
                  onRemove={() => setFilters(f => ({ ...f, category: undefined }))}
                />
              )}
              {filters.capability && (
                <FilterChip
                  label={capabilities.find(c => c.id === filters.capability)?.title || filters.capability}
                  onRemove={() => setFilters(f => ({ ...f, capability: undefined }))}
                />
              )}
              {filters.rating && (
                <FilterChip
                  label={`${filters.rating}+ stars`}
                  onRemove={() => setFilters(f => ({ ...f, rating: undefined }))}
                />
              )}
              {filters.sort && filters.sort !== 'installs_desc' && (
                <FilterChip
                  label={getSortLabel(filters.sort)}
                  onRemove={() => setFilters(f => ({ ...f, sort: undefined }))}
                />
              )}
              <button
                onClick={clearFilters}
                className="text-xs text-purple-primary hover:underline"
              >
                Clear all
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-4 py-6">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 text-purple-primary animate-spin" />
            </div>
          ) : isSearching ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 text-text-tertiary animate-spin" />
            </div>
          ) : activeTab === 'installed' ? (
            // Installed apps view
            <div>
              {installedApps.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-text-tertiary">No installed apps yet</p>
                  <p className="text-sm text-text-quaternary mt-1">
                    Explore and install apps to enhance your Omi experience
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {installedApps.map(app => (
                    <AppCard key={app.id} app={app} onUpdate={handleAppUpdate} />
                  ))}
                </div>
              )}
            </div>
          ) : isShowingSearchResults ? (
            // Search results view
            <div>
              <p className="text-sm text-text-tertiary mb-4">
                {searchResults.length} {searchResults.length === 1 ? 'app' : 'apps'} found
              </p>
              {searchResults.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-text-tertiary">No apps match your search</p>
                  <p className="text-sm text-text-quaternary mt-1">
                    Try different keywords or adjust your filters
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {searchResults.map(app => (
                    <AppCard key={app.id} app={app} onUpdate={handleAppUpdate} />
                  ))}
                </div>
              )}
            </div>
          ) : (
            // Explore view with grouped apps
            <div className="space-y-8">
              {/* Popular apps section */}
              {popularApps.length > 0 && (
                <AppGridSection
                  title="Popular"
                  apps={popularApps.slice(0, 6)}
                  onUpdate={handleAppUpdate}
                />
              )}

              {/* Capability groups */}
              {appGroups
                .filter(group => group.apps && group.apps.length > 0)
                .map(group => (
                  <AppGridSection
                    key={group.capability.id}
                    title={group.capability.title}
                    apps={group.apps.slice(0, 6)}
                    totalCount={group.total}
                    capabilityId={group.capability.id}
                    onUpdate={handleAppUpdate}
                  />
                ))}
            </div>
          )}
        </div>
      </div>

      {/* Filter sheet */}
      <FilterSheet
        open={showFilters}
        onClose={() => setShowFilters(false)}
        filters={filters}
        onFiltersChange={handleFilterChange}
        categories={categories}
        capabilities={capabilities}
      />
    </div>
  );
}

function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-bg-tertiary text-sm text-text-secondary">
      {label}
      <button onClick={onRemove} className="p-0.5 rounded hover:bg-bg-quaternary">
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}

function getSortLabel(sort: SortOption): string {
  switch (sort) {
    case 'rating_desc': return 'Highest rated';
    case 'rating_asc': return 'Lowest rated';
    case 'name_asc': return 'A-Z';
    case 'name_desc': return 'Z-A';
    case 'installs_desc': return 'Most installs';
    default: return sort;
  }
}
