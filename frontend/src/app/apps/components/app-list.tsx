'use client';

import { FeaturedPluginCard } from './plugin-card/featured';
import { CompactPluginCard } from './plugin-card/compact';
import { CategoryHeader } from './category-header';
import type { Plugin, PluginStat } from './types';
import { ChevronRight } from 'lucide-react';
import { ScrollableCategoryNav } from './scrollable-category-nav';
import { SearchBar } from './search/search-bar';
import { useState, useMemo } from 'react';

interface AppListProps {
  initialPlugins: Plugin[];
  initialStats: PluginStat[];
}

// Stable shuffle function using a seed
function seededShuffle<T>(array: T[], seed: number): T[] {
  const shuffled = [...array];
  const random = (i: number) => {
    const x = Math.sin(i + seed) * 10000;
    return x - Math.floor(x);
  };

  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(random(i) * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

export default function AppList({ initialPlugins, initialStats }: AppListProps) {
  const [isSearching, setIsSearching] = useState(false);

  // Use useMemo to ensure consistent results between renders
  const { newThisWeek, mostPopular, integrationApps, sortedCategories } = useMemo(() => {
    // Get new plugins (zero downloads) and shuffle them with a stable seed
    const newPlugins = seededShuffle(
      initialPlugins.filter((plugin) => plugin.installs === 0),
      1, // Fixed seed for consistent shuffling
    ).slice(0, 4);

    // Sort plugins by different criteria
    const mostPopular = [...initialPlugins]
      .sort((a, b) => b.installs - a.installs)
      .slice(0, 9);

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
      newThisWeek: newPlugins,
      mostPopular,
      integrationApps,
      sortedCategories,
    };
  }, [initialPlugins]);

  const totalIntegrationApps = initialPlugins.filter((plugin) =>
    plugin.capabilities.has('external_integration'),
  ).length;

  return (
    <div className="relative">
      {/* Fixed Header and Navigation */}
      <div className="fixed inset-x-0 top-12 z-40 transform-gpu bg-[#0B0F17] transition-all duration-300 ease-in-out">
        <div className="border-b border-white/5">
          <div className="container mx-auto px-3 py-4 sm:px-6 sm:py-6 md:px-8 md:py-8">
            <h1 className="text-2xl font-bold text-[#6C8EEF] sm:text-3xl md:text-4xl">
              Omi App Store
            </h1>
            <p className="mt-2 text-sm text-gray-400 sm:mt-3 sm:text-base">
              Discover our most popular AI-powered applications
            </p>
            <div className="mt-4 sm:mt-6">
              <SearchBar
                allApps={initialPlugins}
                onSearching={(searching) => setIsSearching(searching)}
              />
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
      </div>

      {/* Main Content */}
      {!isSearching && (
        <main className="relative z-0 mt-[16rem] sm:mt-[18rem] md:mt-[20rem]">
          <div className="container mx-auto px-3 py-3 sm:px-6 sm:py-4 md:px-8 md:py-6">
            <div className="space-y-8 sm:space-y-12 md:space-y-16">
              {/* New This Week Section */}
              <section className="pt-6 sm:pt-8 md:pt-10">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold text-white sm:text-2xl">
                    New This Week
                  </h2>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 sm:mt-6 sm:gap-3 lg:grid-cols-4 lg:gap-4">
                  {newThisWeek.map((plugin) => (
                    <FeaturedPluginCard
                      key={plugin.id}
                      plugin={plugin}
                      hideStats={true}
                    />
                  ))}
                </div>
              </section>

              {/* Most Popular Section */}
              <section>
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold text-white sm:text-2xl">
                    Most Popular
                  </h2>
                </div>
                <div className="mt-4 grid grid-cols-1 gap-y-1 sm:mt-6 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3 lg:gap-4">
                  {mostPopular.map((plugin, index) => (
                    <CompactPluginCard
                      key={plugin.id}
                      plugin={plugin}
                      stat={initialStats.find((s) => s.id === plugin.id)}
                      index={index + 1}
                    />
                  ))}
                </div>
              </section>

              {/* Integration Apps Section */}
              {integrationApps.length > 0 && (
                <section>
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
                  <div className="mt-4 grid grid-cols-1 gap-y-1 sm:mt-6 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3 lg:gap-4">
                    {integrationApps.map((plugin, index) => (
                      <CompactPluginCard
                        key={plugin.id}
                        plugin={plugin}
                        stat={initialStats.find((s) => s.id === plugin.id)}
                        index={index + 1}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Category Sections */}
              {Object.entries(sortedCategories).map(([category, plugins]) => (
                <section key={category} id={category}>
                  <div className="flex items-center justify-between">
                    <CategoryHeader category={category} totalApps={plugins.length} />
                    {plugins.length >
                      (category === 'productivity-and-organization' ? 4 : 9) && (
                      <a
                        href={`/apps/category/${category}`}
                        className="flex items-center gap-1 text-sm font-medium text-[#6C8EEF] hover:underline"
                      >
                        See all
                        <ChevronRight className="h-4 w-4" />
                      </a>
                    )}
                  </div>

                  {category === 'productivity-and-organization' ? (
                    // Productivity section with featured tiles
                    <div className="mt-4 grid grid-cols-2 gap-2 sm:mt-6 sm:gap-3 lg:grid-cols-4 lg:gap-4">
                      {plugins.slice(0, 4).map((plugin) => (
                        <FeaturedPluginCard
                          key={plugin.id}
                          plugin={plugin}
                          stat={initialStats.find((s) => s.id === plugin.id)}
                        />
                      ))}
                    </div>
                  ) : (
                    // Other categories with compact tiles
                    <div className="mt-4 grid grid-cols-1 gap-y-1 sm:mt-6 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3 lg:gap-4">
                      {plugins.slice(0, 9).map((plugin, index) => (
                        <CompactPluginCard
                          key={plugin.id}
                          plugin={plugin}
                          stat={initialStats.find((s) => s.id === plugin.id)}
                          index={index + 1}
                        />
                      ))}
                    </div>
                  )}
                </section>
              ))}
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
