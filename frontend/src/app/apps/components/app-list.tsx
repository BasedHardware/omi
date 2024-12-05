import envConfig from '@/src/constants/envConfig';
import { FeaturedPluginCard } from './plugin-card/featured';
import { CompactPluginCard } from './plugin-card/compact';
import { CategoryHeader } from './category-header';
import type { Plugin, PluginStat } from './types';
import { ChevronRight } from 'lucide-react';
import { ScrollableCategoryNav } from './scrollable-category-nav';
import { SearchBar } from './search/search-bar';

async function getPluginsData() {
  const [pluginsResponse, statsResponse] = await Promise.all([
    fetch(`${envConfig.API_URL}/v1/approved-apps?include_reviews=true`, {
      next: { revalidate: 3600 },
    }),
    fetch(
      'https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json',
      {
        next: { revalidate: 3600 },
      },
    ),
  ]);

  const rawPlugins = await pluginsResponse.json();
  if (process.env.NODE_ENV === 'development') {
    console.log('Sample raw plugin data:', {
      name: rawPlugins[0]?.name,
      created_at: rawPlugins[0]?.created_at,
    });
  }

  const plugins = rawPlugins.map((plugin: any) => {
    const { created_at, capabilities, ...rest } = plugin;
    return {
      ...rest,
      created_at,
      capabilities: new Set(capabilities),
    };
  }) as Plugin[];

  if (process.env.NODE_ENV === 'development') {
    console.log('Sample transformed plugin:', {
      name: plugins[0]?.name,
      created_at: plugins[0]?.created_at,
    });
  }

  const stats = (await statsResponse.json()) as PluginStat[];
  return { plugins, stats };
}

export default async function AppList() {
  const { plugins, stats } = await getPluginsData();

  // Get new plugins (zero downloads) and randomize them
  const newPlugins = [...plugins].filter((plugin) => plugin.installs === 0);
  // Shuffle array using Fisher-Yates algorithm
  for (let i = newPlugins.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newPlugins[i], newPlugins[j]] = [newPlugins[j], newPlugins[i]];
  }
  const newThisWeek = newPlugins.slice(0, 4);

  // Sort plugins by different criteria
  const mostPopular = [...plugins].sort((a, b) => b.installs - a.installs).slice(0, 9);

  // Get integration apps
  const integrationApps = [...plugins]
    .filter((plugin) => plugin.capabilities.has('external_integration'))
    .sort((a, b) => b.installs - a.installs)
    .slice(0, 9);

  const totalIntegrationApps = plugins.filter((plugin) =>
    plugin.capabilities.has('external_integration'),
  ).length;

  // Group plugins by category and sort by installs
  const groupedPlugins = plugins.reduce((acc, plugin) => {
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

  return (
    <div className="relative">
      {/* Fixed Header and Navigation */}
      <div className="fixed inset-x-0 top-[50px] z-40 bg-[#0B0F17]">
        <div className="px-6 py-8">
          <div className="container mx-auto">
            <h1 className="text-4xl font-bold text-[#6C8EEF]">Omi App Store</h1>
            <p className="mt-3 text-gray-400">
              Discover our most popular AI-powered applications
            </p>
            <div className="mt-6">
              <SearchBar />
            </div>
          </div>
        </div>

        <div className="border-b border-white/5 shadow-lg shadow-black/5">
          <div className="px-6">
            <div className="container mx-auto py-5">
              <ScrollableCategoryNav currentCategory="" />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="relative z-0 mt-[260px]">
        <div className="px-6 pt-8">
          <div className="container mx-auto">
            <div className="space-y-16">
              {/* New This Week Section */}
              <section>
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold text-white">New This Week</h2>
                </div>
                <div className="mt-6 grid grid-cols-2 gap-3 sm:mt-8 sm:gap-4 lg:grid-cols-4 lg:gap-6">
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
                  <h2 className="text-2xl font-bold text-white">Most Popular</h2>
                </div>
                <div className="mt-6 grid grid-cols-1 gap-y-4 sm:mt-8 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-6 lg:grid-cols-3 lg:gap-x-12">
                  {mostPopular.map((plugin, index) => (
                    <CompactPluginCard
                      key={plugin.id}
                      plugin={plugin}
                      stat={stats.find((s) => s.id === plugin.id)}
                      index={index + 1}
                    />
                  ))}
                </div>
              </section>

              {/* Integration Apps Section */}
              {integrationApps.length > 0 && (
                <section>
                  <div className="flex items-center justify-between">
                    <h3 className="text-xl font-semibold text-white">Integration Apps</h3>
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
                  <div className="mt-6 grid grid-cols-1 gap-y-4 sm:mt-8 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-6 lg:grid-cols-3 lg:gap-x-12">
                    {integrationApps.map((plugin, index) => (
                      <CompactPluginCard
                        key={plugin.id}
                        plugin={plugin}
                        stat={stats.find((s) => s.id === plugin.id)}
                        index={index + 1}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Category Sections */}
              {Object.entries(sortedCategories).map(([category, plugins]) => (
                <section key={category} id={category} className="space-y-8">
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
                    <div className="mt-6 grid grid-cols-2 gap-3 sm:mt-8 sm:gap-4 lg:grid-cols-4 lg:gap-6">
                      {plugins.slice(0, 4).map((plugin) => (
                        <FeaturedPluginCard
                          key={plugin.id}
                          plugin={plugin}
                          stat={stats.find((s) => s.id === plugin.id)}
                        />
                      ))}
                    </div>
                  ) : (
                    // Other categories with compact tiles
                    <div className="mt-6 grid grid-cols-1 gap-y-4 sm:mt-8 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-6 lg:grid-cols-3 lg:gap-x-12">
                      {plugins.slice(0, 9).map((plugin, index) => (
                        <CompactPluginCard
                          key={plugin.id}
                          plugin={plugin}
                          stat={stats.find((s) => s.id === plugin.id)}
                          index={index + 1}
                        />
                      ))}
                    </div>
                  )}
                </section>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
