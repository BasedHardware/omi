'use client';

import { FeaturedPluginCard } from './plugin-card/FeaturedPluginCard';
import { CompactPluginCard } from './plugin-card/CompactPluginCard';
import { CategoryHeader } from './CategoryHeader';
import type { Plugin, PluginStat } from './types';
import { ChevronRight, ChevronUp, Sparkles, Trophy } from 'lucide-react';
import { ScrollableCategoryNav } from './ScrollableCategoryNav';
import { SearchBar } from './SearchBar';
import { useState, useMemo, useEffect, useRef, useCallback, memo } from 'react';
import { DeveloperBanner } from './DeveloperBanner';

interface MarketplaceHeaderProps {
  minimized: boolean;
  onSearching: (searching: boolean) => void;
}

/**
 * Memoized header component to prevent re-renders from scroll state
 * changes from propagating to the entire AppList
 */
const MarketplaceHeader = memo(function MarketplaceHeader({
  minimized,
  onSearching,
}: MarketplaceHeaderProps) {
  return (
    <>
      <div
        className={`border-b border-white/5 transition-all duration-300 ${
          minimized ? 'py-2' : ''
        }`}
      >
        <div className="container mx-auto px-3 py-3 sm:px-6 sm:py-4 md:px-8 md:py-5">
          <div className="flex flex-col transition-all duration-300 sm:flex-row sm:items-center sm:space-x-6">
            {/* Title Section */}
            <div
              className={`flex-shrink-0 transform-gpu transition-all duration-300 ease-in-out ${
                minimized ? 'sm:w-48 md:w-56' : 'w-full sm:w-56 md:w-64'
              }`}
            >
              <h1
                className={`transform-gpu text-2xl font-bold text-[#6C8EEF] transition-all duration-300 ${
                  minimized ? 'text-xl sm:text-2xl' : 'sm:text-3xl md:text-4xl'
                }`}
              >
                Omi App Store
              </h1>
              <div
                className={`transform-gpu overflow-hidden transition-all duration-300 ${
                  minimized ? 'h-0 opacity-0' : 'h-auto opacity-100'
                }`}
              >
                <p className="mt-1 text-sm text-gray-400 sm:mt-2 sm:text-base">
                  Discover our most popular AI-powered applications
                </p>
              </div>
            </div>

            {/* Search Section */}
            <div
              className={`flex-grow transform-gpu transition-all duration-300 ${
                minimized ? 'mt-0' : 'mt-4 sm:mt-0'
              }`}
            >
              <SearchBar onSearching={onSearching} />
            </div>
          </div>
        </div>
      </div>

      <div className="border-b border-white/5 bg-[#0B0F17]/80 backdrop-blur-sm">
        <div className="container mx-auto px-3 sm:px-6 md:px-8">
          <div className="py-2 sm:py-2.5 md:py-3">
            <ScrollableCategoryNav currentCategory="" />
          </div>
        </div>
      </div>
    </>
  );
});

interface AppListProps {
  initialPlugins: Plugin[];
  initialStats: PluginStat[];
}

export default function AppList({ initialPlugins, initialStats }: AppListProps) {
  const [isSearching, setIsSearching] = useState(false);
  const [headerMinimized, setHeaderMinimized] = useState(false);
  const headerRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLDivElement>(null);

  // Handle scroll behavior for header
  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 100) {
        setHeaderMinimized(true);
      } else {
        setHeaderMinimized(false);
      }
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Use useMemo to ensure consistent results between renders
  const { featuredApps, mostPopular, integrationApps, sortedCategories } = useMemo(() => {
    // Get featured apps from API's is_popular field, sorted by installs
    // Take top 3 for the featured section
    const featured = [...initialPlugins]
      .filter((plugin) => plugin.is_popular)
      .sort((a, b) => b.installs - a.installs)
      .slice(0, 3);

    // Get all popular apps from API's is_popular field, sorted by installs
    const mostPopular = [...initialPlugins]
      .filter((plugin) => plugin.is_popular)
      .sort((a, b) => b.installs - a.installs);

    // Get integration apps
    const integrationApps = [...initialPlugins]
      .filter((plugin) => plugin.capabilities.has('external_integration'))
      .sort((a, b) => b.installs - a.installs)
      .slice(0, 9);

    // Group plugins by category and sort by installs
    const groupedPlugins = initialPlugins.reduce((acc, plugin) => {
      const category = plugin.category;
      if (!acc[category]) {
        acc[category] = [];
      }
      acc[category].push(plugin);
      return acc;
    }, {} as Record<string, Plugin[]>);

    // Sort categories by number of plugins
    const sortedCategories = Object.entries(groupedPlugins)
      .sort(([, a], [, b]) => b.length - a.length)
      .reduce((acc, [category, plugins]) => {
        acc[category] = plugins.sort((a, b) => b.installs - a.installs);
        return acc;
      }, {} as Record<string, Plugin[]>);

    return {
      featuredApps: featured,
      mostPopular,
      integrationApps,
      sortedCategories,
    };
  }, [initialPlugins]);

  const totalIntegrationApps = initialPlugins.filter((plugin) =>
    plugin.capabilities.has('external_integration'),
  ).length;

  // Function to scroll back to top - memoized to prevent recreation on every render
  const scrollToTop = useCallback(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  // Stable callback for search state changes
  const handleSearching = useCallback((searching: boolean) => {
    setIsSearching(searching);
  }, []);

  return (
    <div className="relative">
      {/* Fixed Header and Navigation */}
      <div
        ref={headerRef}
        className={`fixed inset-x-0 top-12 z-40 transform-gpu bg-[#0B0F17] transition-all duration-300 ease-in-out ${
          headerMinimized ? 'bg-[#0B0F17]/95 shadow-lg backdrop-blur-lg' : ''
        }`}
      >
        <MarketplaceHeader
          minimized={headerMinimized}
          onSearching={handleSearching}
        />
      </div>

      {/* Main Content */}
      {!isSearching && (
        <main
          className={`relative z-0 ${
            headerMinimized
              ? 'mt-[8rem] sm:mt-[8.5rem] md:mt-[9rem]'
              : 'mt-[11rem] sm:mt-[12rem] md:mt-[13rem]'
          } transition-all duration-300`}
        >
          {/* Hero Section */}
          <div
            ref={heroRef}
            className="relative mb-12 bg-gradient-to-b from-[#131A29] to-[#0B0F17] py-8 sm:py-10 md:py-12"
          >
            <div className="container mx-auto px-3 sm:px-6 md:px-8">
              <div className="mb-6 flex items-center">
                <Sparkles className="mr-2 h-5 w-5 text-[#6C8EEF]" />
                <h2 className="text-lg font-bold text-white sm:text-xl md:text-2xl">
                  Featured Applications
                </h2>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {featuredApps.map((plugin) => (
                  <div
                    key={plugin.id}
                    className="h-full transform transition-transform duration-300 hover:scale-[1.02]"
                  >
                    <FeaturedPluginCard plugin={plugin} />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="container mx-auto px-3 py-3 sm:px-6 sm:py-4 md:px-8 md:py-6">
            <div className="space-y-12 sm:space-y-16 md:space-y-20">
              {/* Developer Banner */}
              <section className="mb-8">
                <DeveloperBanner />
              </section>
              {/* Most Popular Section */}
              <section className="relative rounded-xl p-4 sm:p-6 md:p-8">
                <div className="absolute inset-0 -z-10 rounded-xl bg-gradient-to-r from-[#1A1F2E]/50 to-[#0B0F17] opacity-50"></div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <Trophy className="mr-2 h-5 w-5 text-amber-400" />
                    <h2 className="text-xl font-bold text-white sm:text-2xl">
                      Most Popular
                    </h2>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-1 gap-y-2 sm:mt-6 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                  {mostPopular.map((plugin, index) => (
                    <CompactPluginCard
                      key={plugin.id}
                      plugin={plugin}
                      index={index + 1}
                    />
                  ))}
                </div>
              </section>

              {/* Productivity Section - Moved to top */}
              {sortedCategories['productivity-and-organization'] && (
                <section
                  id="productivity-and-organization"
                  className="rounded-xl bg-[#0F1420]/50 p-4 sm:p-6 md:p-8"
                >
                  <div className="flex items-center justify-between">
                    <CategoryHeader
                      category="productivity-and-organization"
                      totalApps={sortedCategories['productivity-and-organization'].length}
                    />
                    {sortedCategories['productivity-and-organization'].length > 4 && (
                      <a
                        href="/apps/category/productivity-and-organization"
                        className="flex items-center gap-1 text-sm font-medium text-[#6C8EEF] hover:underline"
                      >
                        See all
                        <ChevronRight className="h-4 w-4" />
                      </a>
                    )}
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:mt-6 sm:gap-4 lg:grid-cols-4">
                    {sortedCategories['productivity-and-organization']
                      ?.slice(0, 4)
                      .map((plugin) => (
                        <div key={plugin.id} className="h-full">
                          <FeaturedPluginCard plugin={plugin} />
                        </div>
                      ))}
                  </div>
                </section>
              )}

              {/* Integration Apps Section */}
              {integrationApps.length > 0 && (
                <section className="rounded-xl bg-[#0F1420]/50 p-4 sm:p-6 md:p-8">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-white sm:text-xl">
                      Integration Apps
                    </h3>
                    {totalIntegrationApps > 9 && (
                      <a
                        href="/apps/category/integration"
                        className="flex items-center gap-1 text-sm font-medium text-[#6C8EEF] hover:underline"
                      >
                        See all
                        <ChevronRight className="h-4 w-4" />
                      </a>
                    )}
                  </div>
                  <div className="mt-4 grid grid-cols-1 gap-y-2 sm:mt-6 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                    {integrationApps.map((plugin, index) => (
                      <CompactPluginCard
                        key={plugin.id}
                        plugin={plugin}
                        index={index + 1}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Category Sections - Excluding productivity */}
              {Object.entries(sortedCategories)
                .filter(([category]) => category !== 'productivity-and-organization')
                .map(([category, plugins], idx) => (
                  <section
                    key={category}
                    id={category}
                    className={`rounded-xl ${
                      idx % 2 === 0
                        ? 'bg-[#0F1420]/50'
                        : 'bg-gradient-to-r from-[#131A29]/30 to-[#0B0F17]'
                    } p-4 sm:p-6 md:p-8`}
                  >
                    <div className="flex items-center justify-between">
                      <CategoryHeader category={category} totalApps={plugins.length} />
                      {plugins.length > 9 && (
                        <a
                          href={`/apps/category/${category}`}
                          className="flex items-center gap-1 text-sm font-medium text-[#6C8EEF] hover:underline"
                        >
                          See all
                          <ChevronRight className="h-4 w-4" />
                        </a>
                      )}
                    </div>
                    <div className="mt-4 grid grid-cols-1 gap-y-2 sm:mt-6 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                      {plugins.slice(0, 9).map((plugin, index) => (
                        <CompactPluginCard
                          key={plugin.id}
                          plugin={plugin}
                          index={index + 1}
                        />
                      ))}
                    </div>
                  </section>
                ))}
            </div>
          </div>

          {/* Back to top button */}
          <button
            onClick={scrollToTop}
            className="fixed bottom-6 right-6 z-50 flex h-10 w-10 items-center justify-center rounded-full bg-[#6C8EEF] text-white shadow-lg transition-all duration-300 hover:bg-[#5A7DD9]"
            aria-label="Back to top"
          >
            <ChevronUp className="h-5 w-5" />
          </button>
        </main>
      )}
    </div>
  );
}
