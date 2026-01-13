'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Loader2, X, ChevronDown, Star, Plus, LayoutGrid } from 'lucide-react';
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
import { PageHeader } from '@/components/layout/PageHeader';

// Module-level cache for apps data
interface AppsCache {
  appGroups: AppGroup[];
  popularApps: App[];
  categories: AppCategory[];
  capabilities: AppCapability[];
  installedApps: App[];
  myApps: App[];
  timestamp: number;
}

const appsCache: Partial<AppsCache> = {};
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function isCacheValid(key: keyof AppsCache): boolean {
  if (!appsCache.timestamp) return false;
  if (!appsCache[key]) return false;
  return Date.now() - appsCache.timestamp < CACHE_TTL;
}

function isCacheStale(): boolean {
  if (!appsCache.timestamp) return true;
  return Date.now() - appsCache.timestamp > CACHE_TTL;
}

type Tab = 'explore' | 'installed' | 'my-apps';

// Quick filter dropdown component
function FilterDropdown({
  label,
  value,
  options,
  onChange,
  placeholder,
}: {
  label: string;
  value?: string;
  options: { id: string; title: string }[];
  onChange: (value: string | undefined) => void;
  placeholder?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedOption = options.find(o => o.id === value);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors',
          value
            ? 'bg-purple-primary/10 text-purple-primary border border-purple-primary/30'
            : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary border border-transparent'
        )}
      >
        <span>{selectedOption?.title || label}</span>
        <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full left-0 mt-1 z-20 min-w-[180px] max-h-[300px] overflow-y-auto bg-bg-secondary border border-bg-tertiary rounded-lg shadow-lg py-1">
            <button
              onClick={() => {
                onChange(undefined);
                setIsOpen(false);
              }}
              className={cn(
                'w-full px-3 py-2 text-left text-sm hover:bg-bg-tertiary transition-colors',
                !value ? 'text-purple-primary' : 'text-text-secondary'
              )}
            >
              {placeholder || `All ${label}s`}
            </button>
            {options.map(option => (
              <button
                key={option.id}
                onClick={() => {
                  onChange(option.id);
                  setIsOpen(false);
                }}
                className={cn(
                  'w-full px-3 py-2 text-left text-sm hover:bg-bg-tertiary transition-colors',
                  value === option.id ? 'text-purple-primary' : 'text-text-primary'
                )}
              >
                {option.title}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// Rating filter dropdown
function RatingFilter({
  value,
  onChange,
}: {
  value?: number;
  onChange: (value: number | undefined) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const ratings = [4, 3, 2, 1];

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors',
          value
            ? 'bg-purple-primary/10 text-purple-primary border border-purple-primary/30'
            : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary border border-transparent'
        )}
      >
        <Star className="w-4 h-4" />
        <span>{value ? `${value}+` : 'Rating'}</span>
        <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full left-0 mt-1 z-20 min-w-[120px] bg-bg-secondary border border-bg-tertiary rounded-lg shadow-lg py-1">
            <button
              onClick={() => {
                onChange(undefined);
                setIsOpen(false);
              }}
              className={cn(
                'w-full px-3 py-2 text-left text-sm hover:bg-bg-tertiary transition-colors',
                !value ? 'text-purple-primary' : 'text-text-secondary'
              )}
            >
              Any rating
            </button>
            {ratings.map(rating => (
              <button
                key={rating}
                onClick={() => {
                  onChange(rating);
                  setIsOpen(false);
                }}
                className={cn(
                  'w-full px-3 py-2 text-left text-sm hover:bg-bg-tertiary transition-colors flex items-center gap-1',
                  value === rating ? 'text-purple-primary' : 'text-text-primary'
                )}
              >
                {rating}+ <Star className="w-3 h-3 fill-current" />
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// Sort dropdown
function SortDropdown({
  value,
  onChange,
}: {
  value?: SortOption;
  onChange: (value: SortOption | undefined) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const sortOptions: { id: SortOption; label: string }[] = [
    { id: 'installs_desc', label: 'Most popular' },
    { id: 'rating_desc', label: 'Highest rated' },
    { id: 'name_asc', label: 'A-Z' },
    { id: 'name_desc', label: 'Z-A' },
  ];
  const selected = sortOptions.find(o => o.id === value);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors',
          value && value !== 'installs_desc'
            ? 'bg-purple-primary/10 text-purple-primary border border-purple-primary/30'
            : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary border border-transparent'
        )}
      >
        <span>{selected?.label || 'Sort'}</span>
        <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full right-0 mt-1 z-20 min-w-[150px] bg-bg-secondary border border-bg-tertiary rounded-lg shadow-lg py-1">
            {sortOptions.map(option => (
              <button
                key={option.id}
                onClick={() => {
                  onChange(option.id === 'installs_desc' ? undefined : option.id);
                  setIsOpen(false);
                }}
                className={cn(
                  'w-full px-3 py-2 text-left text-sm hover:bg-bg-tertiary transition-colors',
                  value === option.id || (!value && option.id === 'installs_desc')
                    ? 'text-purple-primary'
                    : 'text-text-primary'
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function AppsExplorer() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>('explore');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');

  // Initialize from cache - only show loading if no cached data
  const hasExploreCache = isCacheValid('appGroups');
  const [isLoading, setIsLoading] = useState(!hasExploreCache);
  const [isSearching, setIsSearching] = useState(false);

  // Data - initialize from cache
  const [appGroups, setAppGroups] = useState<AppGroup[]>(appsCache.appGroups || []);
  const [popularApps, setPopularApps] = useState<App[]>(appsCache.popularApps || []);
  const [searchResults, setSearchResults] = useState<App[]>([]);
  const [installedApps, setInstalledApps] = useState<App[]>(appsCache.installedApps || []);
  const [myApps, setMyApps] = useState<App[]>(appsCache.myApps || []);
  const [categories, setCategories] = useState<AppCategory[]>(appsCache.categories || []);
  const [capabilities, setCapabilities] = useState<AppCapability[]>(appsCache.capabilities || []);

  // Track if fetch is in progress
  const fetchingRef = useRef(false);

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
    async function loadData(backgroundRefresh = false) {
      if (fetchingRef.current) return;
      fetchingRef.current = true;

      if (!backgroundRefresh) {
        setIsLoading(true);
      }

      try {
        const [groupedData, popular, cats, caps] = await Promise.all([
          getAppsGrouped(),
          getPopularApps(),
          getAppCategories(),
          getAppCapabilities(),
        ]);

        const groups = groupedData.groups || [];
        const popularList = popular || [];
        const catsList = cats || [];
        const capsList = caps || [];

        setAppGroups(groups);
        setPopularApps(popularList);
        setCategories(catsList);
        setCapabilities(capsList);

        // Update cache
        appsCache.appGroups = groups;
        appsCache.popularApps = popularList;
        appsCache.categories = catsList;
        appsCache.capabilities = capsList;
        appsCache.timestamp = Date.now();
      } catch (err) {
        console.error('Failed to load apps:', err);
      } finally {
        setIsLoading(false);
        fetchingRef.current = false;
      }
    }

    // If we have fresh cache, skip fetch
    if (isCacheValid('appGroups')) {
      setIsLoading(false);
      // If stale, do background refresh
      if (isCacheStale()) {
        loadData(true);
      }
      return;
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
          my_apps: activeTab === 'my-apps' ? true : undefined,
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
    async function loadInstalled(backgroundRefresh = false) {
      if (activeTab !== 'installed') return;

      if (!backgroundRefresh) {
        setIsLoading(true);
      }

      try {
        const response = await searchApps({ installed_apps: true, limit: 100 });
        const apps = response.data || [];
        setInstalledApps(apps);
        appsCache.installedApps = apps;
        appsCache.timestamp = Date.now();
      } catch (err) {
        console.error('Failed to load installed apps:', err);
      } finally {
        setIsLoading(false);
      }
    }

    if (activeTab === 'installed') {
      // Check cache first
      if (isCacheValid('installedApps')) {
        setInstalledApps(appsCache.installedApps!);
        setIsLoading(false);
        if (isCacheStale()) {
          loadInstalled(true);
        }
        return;
      }
      loadInstalled();
    }
  }, [activeTab]);

  // Load my apps when switching to my-apps tab
  useEffect(() => {
    async function loadMyApps(backgroundRefresh = false) {
      if (activeTab !== 'my-apps') return;

      if (!backgroundRefresh) {
        setIsLoading(true);
      }

      try {
        const response = await searchApps({ my_apps: true, limit: 100 });
        const apps = response.data || [];
        setMyApps(apps);
        appsCache.myApps = apps;
        appsCache.timestamp = Date.now();
      } catch (err) {
        console.error('Failed to load my apps:', err);
      } finally {
        setIsLoading(false);
      }
    }

    if (activeTab === 'my-apps') {
      // Check cache first
      if (isCacheValid('myApps')) {
        setMyApps(appsCache.myApps!);
        setIsLoading(false);
        if (isCacheStale()) {
          loadMyApps(true);
        }
        return;
      }
      loadMyApps();
    }
  }, [activeTab]);

  const clearFilters = useCallback(() => {
    setFilters({});
    setSearchQuery('');
  }, []);

  // Refresh app list after enable/disable
  const handleAppUpdate = useCallback(async () => {
    if (activeTab === 'installed') {
      const response = await searchApps({ installed_apps: true, limit: 100 });
      const apps = response.data || [];
      setInstalledApps(apps);
      appsCache.installedApps = apps;
    } else if (activeTab === 'my-apps') {
      const response = await searchApps({ my_apps: true, limit: 100 });
      const apps = response.data || [];
      setMyApps(apps);
      appsCache.myApps = apps;
    }
    // Refresh groups to update enabled state
    const groupedData = await getAppsGrouped();
    const groups = groupedData.groups || [];
    setAppGroups(groups);
    appsCache.appGroups = groups;

    // Refresh popular apps too
    const popular = await getPopularApps();
    const popularList = popular || [];
    setPopularApps(popularList);
    appsCache.popularApps = popularList;

    appsCache.timestamp = Date.now();
  }, [activeTab]);

  const isShowingSearchResults = debouncedQuery.trim().length > 0 || activeFilterCount > 0;

  // Get group title from capability or category
  const getGroupTitle = (group: AppGroup): string => {
    return group.capability?.title || group.category?.title || 'Apps';
  };

  // Get group ID from capability or category
  const getGroupId = (group: AppGroup): string => {
    return group.capability?.id || group.category?.id || 'unknown';
  };

  // Get apps to display based on current tab
  const getAppsForCurrentTab = (): App[] => {
    if (activeTab === 'installed') return installedApps;
    if (activeTab === 'my-apps') return myApps;
    return [];
  };

  const getEmptyMessage = () => {
    if (activeTab === 'installed') {
      return {
        title: 'No installed apps yet',
        subtitle: 'Explore and install apps to enhance your Omi experience',
      };
    }
    if (activeTab === 'my-apps') {
      return {
        title: 'No apps created yet',
        subtitle: 'Create your own apps to customize your Omi experience',
      };
    }
    return { title: '', subtitle: '' };
  };

  return (
    <div className="min-h-full">
      {/* Page Header */}
      <PageHeader title="Apps" icon={LayoutGrid} />

      {/* Sticky Toolbar */}
      <div className="sticky top-0 z-10 border-b border-bg-tertiary bg-bg-secondary">
        <div className="py-4 px-4">
          {/* Tabs + Create button */}
          <div className="flex items-center gap-1 mb-4">
            {/* Tabs */}
            <button
              onClick={() => setActiveTab('explore')}
              className={cn(
                'px-4 py-2 rounded-xl text-sm font-medium transition-colors',
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
                'px-4 py-2 rounded-xl text-sm font-medium transition-colors',
                activeTab === 'installed'
                  ? 'bg-purple-primary text-white'
                  : 'text-text-secondary hover:bg-bg-tertiary'
              )}
            >
              Installed
            </button>
            <button
              onClick={() => setActiveTab('my-apps')}
              className={cn(
                'px-4 py-2 rounded-xl text-sm font-medium transition-colors',
                activeTab === 'my-apps'
                  ? 'bg-purple-primary text-white'
                  : 'text-text-secondary hover:bg-bg-tertiary'
              )}
            >
              My Apps
            </button>

            {/* Spacer + Create button */}
            <div className="flex-1" />
            <button
              onClick={() => router.push('/apps/new')}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-xl',
                'bg-purple-primary text-white font-medium',
                'hover:bg-purple-primary/90 transition-colors'
              )}
            >
              <Plus className="w-5 h-5" />
              <span className="hidden sm:inline">Create App</span>
            </button>
          </div>

          {/* Search */}
          <div className="relative mb-3">
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

          {/* Inline Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <FilterDropdown
              label="Category"
              value={filters.category}
              options={categories}
              onChange={(v) => setFilters(f => ({ ...f, category: v }))}
              placeholder="All categories"
            />
            <FilterDropdown
              label="Capability"
              value={filters.capability}
              options={capabilities}
              onChange={(v) => setFilters(f => ({ ...f, capability: v }))}
              placeholder="All capabilities"
            />
            <RatingFilter
              value={filters.rating}
              onChange={(v) => setFilters(f => ({ ...f, rating: v }))}
            />
            <SortDropdown
              value={filters.sort}
              onChange={(v) => setFilters(f => ({ ...f, sort: v }))}
            />
            {activeFilterCount > 0 && (
              <button
                onClick={clearFilters}
                className="text-sm text-purple-primary hover:underline ml-2"
              >
                Clear all
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="w-full px-6 py-6">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 text-purple-primary animate-spin" />
          </div>
        ) : isSearching ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 text-text-tertiary animate-spin" />
          </div>
        ) : activeTab === 'installed' || activeTab === 'my-apps' ? (
          // Installed or My Apps view
          <div>
            {isShowingSearchResults ? (
              // Search results within tab
              <>
                <p className="text-sm text-text-tertiary mb-4">
                  {searchResults.length} {searchResults.length === 1 ? 'app' : 'apps'} found
                </p>
                {searchResults.length === 0 ? (
                  <div className="text-center py-12">
                    <p className="text-text-tertiary">No apps match your search</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {searchResults.map(app => (
                      <AppCard key={app.id} app={app} onUpdate={handleAppUpdate} />
                    ))}
                  </div>
                )}
              </>
            ) : getAppsForCurrentTab().length === 0 ? (
              <div className="text-center py-12">
                <p className="text-text-tertiary">{getEmptyMessage().title}</p>
                <p className="text-sm text-text-quaternary mt-1">
                  {getEmptyMessage().subtitle}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {getAppsForCurrentTab().map(app => (
                  <AppCard key={app.id} app={app} onUpdate={handleAppUpdate} />
                ))}
              </div>
            )}
          </div>
        ) : isShowingSearchResults ? (
          // Search results view (explore tab)
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
          <div className="space-y-8 pb-8">
            {/* Popular apps section */}
            {popularApps.length > 0 && (
              <AppGridSection
                title="Popular"
                apps={popularApps.slice(0, 6)}
                onUpdate={handleAppUpdate}
              />
            )}

            {/* Capability/Category groups */}
            {appGroups
              .filter(group => group.data && group.data.length > 0)
              .map(group => (
                <AppGridSection
                  key={getGroupId(group)}
                  title={getGroupTitle(group)}
                  apps={group.data.slice(0, 6)}
                  totalCount={group.pagination?.total}
                  capabilityId={group.capability?.id}
                  onUpdate={handleAppUpdate}
                />
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
